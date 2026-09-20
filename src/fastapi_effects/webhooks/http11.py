"""Bounded HTTP/1.1 response parsing that never retains receiver bodies."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import NoReturn

from fastapi_effects.errors import PermanentDeliveryError, RetryableDeliveryError

_STATUS_LINE = re.compile(rb"^HTTP/1\.[01] ([0-9]{3})(?: [\x20-\x7e]*)?\r\n$")
_HEADER_NAME = re.compile(rb"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


@dataclass(frozen=True, slots=True)
class ResponseLimits:
    read_timeout_seconds: float = 10.0
    maximum_header_bytes: int = 32 * 1024
    maximum_header_count: int = 128
    maximum_informational_responses: int = 8
    maximum_body_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if not 0 < self.read_timeout_seconds <= 300:
            raise ValueError("HTTP read timeout must be in (0, 300].")
        for value in (
            self.maximum_header_bytes,
            self.maximum_header_count,
            self.maximum_informational_responses,
            self.maximum_body_bytes,
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError("HTTP response byte/count bounds must be positive.")


@dataclass(frozen=True, slots=True)
class HttpResponseMetadata:
    status_code: int
    headers: Mapping[str, str]
    discarded_body_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


async def parse_response(
    reader: asyncio.StreamReader,
    *,
    limits: ResponseLimits,
) -> HttpResponseMetadata:
    budget = limits.maximum_header_bytes
    count = 0
    informational_count = 0
    while True:
        status_line = await _readline(reader, limits.read_timeout_seconds, budget)
        budget -= len(status_line)
        match = _STATUS_LINE.fullmatch(status_line)
        if match is None:
            _malformed()
        status = int(match.group(1))
        headers: dict[str, str] = {}
        while True:
            line = await _readline(reader, limits.read_timeout_seconds, budget)
            budget -= len(line)
            if line == b"\r\n":
                break
            count += 1
            if count > limits.maximum_header_count or line[:1] in {b" ", b"\t"}:
                _oversized()
            name, separator, raw_value = line[:-2].partition(b":")
            if not separator or _HEADER_NAME.fullmatch(name) is None:
                _malformed()
            try:
                key = name.decode("ascii").lower()
                value = raw_value.strip(b" \t").decode("latin-1")
            except UnicodeError:
                _malformed()
            if "\r" in value or "\n" in value or "\x00" in value:
                _malformed()
            if key in headers:
                if key == "content-length" and headers[key] != value:
                    _malformed()
                headers[key] = f"{headers[key]}, {value}"
            else:
                headers[key] = value

        if status == 101:
            _unsupported_upgrade()
        if 100 <= status < 200:
            informational_count += 1
            if informational_count > limits.maximum_informational_responses:
                _oversized()
            continue
        break

    discarded = await _discard_body(reader, status=status, headers=headers, limits=limits)
    return HttpResponseMetadata(
        status_code=status,
        headers=headers,
        discarded_body_bytes=discarded,
    )


async def _discard_body(
    reader: asyncio.StreamReader,
    *,
    status: int,
    headers: Mapping[str, str],
    limits: ResponseLimits,
) -> int:
    if 100 <= status < 200 or status in {204, 304}:
        return 0
    transfer = headers.get("transfer-encoding")
    if transfer is not None:
        if transfer.lower().strip() != "chunked":
            _malformed()
        return await _discard_chunked(reader, limits)
    content_length = headers.get("content-length")
    if content_length is not None:
        if not content_length.isdigit():
            _malformed()
        length = int(content_length)
        if length > limits.maximum_body_bytes:
            _oversized()
        await _readexactly(reader, length, limits.read_timeout_seconds)
        return length
    total = 0
    while True:
        try:
            chunk = await asyncio.wait_for(
                reader.read(min(8192, limits.maximum_body_bytes - total + 1)),
                timeout=limits.read_timeout_seconds,
            )
        except TimeoutError as exc:
            raise RetryableDeliveryError(
                code="webhook.response_timeout",
                summary="Webhook receiver response timed out.",
            ) from exc
        if not chunk:
            return total
        total += len(chunk)
        if total > limits.maximum_body_bytes:
            _oversized()


async def _discard_chunked(reader: asyncio.StreamReader, limits: ResponseLimits) -> int:
    total = 0
    trailer_budget = limits.maximum_header_bytes
    trailer_count = 0
    while True:
        line = await _readline(reader, limits.read_timeout_seconds, 1024)
        raw_size = line[:-2].partition(b";")[0]
        try:
            size = int(raw_size, 16)
        except ValueError:
            _malformed()
        if size < 0 or total + size > limits.maximum_body_bytes:
            _oversized()
        if size == 0:
            while True:
                trailer = await _readline(
                    reader,
                    limits.read_timeout_seconds,
                    trailer_budget,
                )
                trailer_budget -= len(trailer)
                if trailer == b"\r\n":
                    return total
                trailer_count += 1
                if trailer_count > limits.maximum_header_count or b":" not in trailer:
                    _oversized()
        await _readexactly(reader, size, limits.read_timeout_seconds)
        if await _readexactly(reader, 2, limits.read_timeout_seconds) != b"\r\n":
            _malformed()
        total += size


async def _readline(
    reader: asyncio.StreamReader,
    timeout_seconds: float,
    budget: int,
) -> bytes:
    if budget < 2:
        _oversized()
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=timeout_seconds)
    except (TimeoutError, ValueError) as exc:
        raise RetryableDeliveryError(
            code="webhook.response_bounds",
            summary="Webhook receiver response exceeded safe bounds.",
        ) from exc
    if not line or len(line) > budget or not line.endswith(b"\r\n"):
        _oversized()
    return line


async def _readexactly(
    reader: asyncio.StreamReader,
    size: int,
    timeout_seconds: float,
) -> bytes:
    try:
        return await asyncio.wait_for(reader.readexactly(size), timeout=timeout_seconds)
    except (TimeoutError, asyncio.IncompleteReadError) as exc:
        raise RetryableDeliveryError(
            code="webhook.response_incomplete",
            summary="Webhook receiver closed an incomplete response.",
        ) from exc


def _oversized() -> NoReturn:
    raise RetryableDeliveryError(
        code="webhook.response_bounds",
        summary="Webhook receiver response exceeded safe bounds.",
    )


def _malformed() -> NoReturn:
    raise RetryableDeliveryError(
        code="webhook.response_malformed",
        summary="Webhook receiver returned malformed HTTP.",
    )


def _unsupported_upgrade() -> NoReturn:
    raise PermanentDeliveryError(
        code="webhook.protocol_upgrade_unsupported",
        summary="Webhook receiver requested an unsupported protocol upgrade.",
    )


__all__ = ["HttpResponseMetadata", "ResponseLimits", "parse_response"]

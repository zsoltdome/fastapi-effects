"""Strict bounded request fingerprinting and opaque key identity."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.sqlalchemy.canonical import (
    canonical_json_bytes,
    strict_json_loads,
    versioned_canonical_bytes,
)

FINGERPRINT_VERSION = 1
MAX_COMMAND_BODY_BYTES = 1024 * 1024
_HEADER_NAME = re.compile(r"^[a-z0-9!#$%&'*+\-.^_`|~]{1,128}$")
_FORBIDDEN_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "idempotency-key",
}


class BodyFingerprintMode(StrEnum):
    RAW = "raw"
    CANONICAL_JSON = "canonical_json"


@dataclass(frozen=True, slots=True)
class RequestFingerprint:
    version: int
    digest: bytes

    def __post_init__(self) -> None:
        if (
            self.version != FINGERPRINT_VERSION
            or not isinstance(self.digest, bytes)
            or len(self.digest) != 32
        ):
            raise MergenConfigurationError("Command request fingerprint is invalid.")

    @classmethod
    def from_hex(cls, value: str) -> RequestFingerprint:
        if not isinstance(value, str):
            raise MergenConfigurationError("Command request fingerprint is invalid.")
        try:
            digest = bytes.fromhex(value)
        except ValueError as exc:
            raise MergenConfigurationError("Command request fingerprint is invalid.") from exc
        return cls(version=FINGERPRINT_VERSION, digest=digest)

    @property
    def hex_digest(self) -> str:
        return self.digest.hex()


def fingerprint_request(
    *,
    path_parameters: Mapping[str, str],
    raw_query: bytes,
    headers: Mapping[str, str] | Sequence[tuple[str, str]],
    media_type: str | None,
    body: bytes,
    mode: BodyFingerprintMode,
    maximum_body_bytes: int = MAX_COMMAND_BODY_BYTES,
) -> RequestFingerprint:
    if (
        not isinstance(maximum_body_bytes, int)
        or isinstance(maximum_body_bytes, bool)
        or maximum_body_bytes < 1
    ):
        raise MergenConfigurationError("Command request body limit is invalid.")
    if not isinstance(raw_query, bytes) or len(raw_query) > 16 * 1024:
        raise MergenConfigurationError("Command query representation is oversized.")
    if not isinstance(body, bytes) or len(body) > maximum_body_bytes:
        raise MergenConfigurationError("Command request body is oversized.")
    normalized_path = _path_parameters(path_parameters)
    normalized_headers = _headers(headers)
    if mode is BodyFingerprintMode.CANONICAL_JSON:
        parsed = strict_json_loads(body, maximum_bytes=maximum_body_bytes)
        body_identity = versioned_canonical_bytes(parsed, maximum_bytes=maximum_body_bytes)
    elif mode is BodyFingerprintMode.RAW:
        body_identity = b"fastapi-mergen:command-raw:v1\n" + body
    else:
        raise MergenConfigurationError("Command body fingerprint mode is invalid.")
    representation = canonical_json_bytes(
        {
            "body_mode": mode.value,
            "body_sha256": hashlib.sha256(body_identity).hexdigest(),
            "headers": normalized_headers,
            "media_type": _media_type(media_type),
            "path_parameters": normalized_path,
            "query_base64": base64.b64encode(raw_query).decode("ascii"),
            "version": FINGERPRINT_VERSION,
        },
        maximum_bytes=64 * 1024,
    )
    return RequestFingerprint(
        version=FINGERPRINT_VERSION,
        digest=hashlib.sha256(representation).digest(),
    )


def _path_parameters(value: Mapping[str, str]) -> dict[str, str]:
    if len(value) > 64:
        raise MergenConfigurationError("Command path parameters are oversized.")
    result: dict[str, str] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 128
            or not isinstance(item, str)
            or len(item.encode("utf-8")) > 4096
        ):
            raise MergenConfigurationError("Command path parameter is invalid.")
        result[key] = item
    return result


def _headers(value: Mapping[str, str] | Sequence[tuple[str, str]]) -> dict[str, str]:
    items = value.items() if isinstance(value, Mapping) else value
    result: dict[str, str] = {}
    for raw_name, raw_value in items:
        if not isinstance(raw_name, str):
            raise MergenConfigurationError("Command representation header is invalid.")
        name = raw_name.lower()
        if (
            not _HEADER_NAME.fullmatch(name)
            or name in _FORBIDDEN_HEADERS
            or name in result
            or not isinstance(raw_value, str)
            or len(raw_value) > 4096
            or any(character in raw_value for character in "\r\n\x00")
        ):
            raise MergenConfigurationError("Command representation header is invalid.")
        result[name] = " ".join(raw_value.strip().split())
    return result


def _media_type(value: str | None) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 128
        or any(character in value for character in "\r\n\x00")
    ):
        raise MergenConfigurationError("Command media type is invalid.")
    return value.lower().strip()


__all__ = [
    "FINGERPRINT_VERSION",
    "MAX_COMMAND_BODY_BYTES",
    "BodyFingerprintMode",
    "RequestFingerprint",
    "fingerprint_request",
]

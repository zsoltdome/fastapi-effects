"""Bounded FastAPI request preparation for command transactions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from starlette.requests import Request

from fastapi_effects.core.principal import Principal
from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.idempotency.fingerprint import (
    MAX_COMMAND_BODY_BYTES,
    BodyFingerprintMode,
    RequestFingerprint,
    fingerprint_request,
)
from fastapi_effects.idempotency.models import CommandIdentity

_HEADER_NAME = re.compile(rb"^[a-z0-9!#$%&'*+\-.^_`|~]{1,128}$")


@dataclass(frozen=True, slots=True)
class PreparedCommand:
    identity: CommandIdentity
    fingerprint: RequestFingerprint


async def prepare_request(
    request: Request,
    *,
    principal: Principal,
    route_id: str,
    body_mode: BodyFingerprintMode = BodyFingerprintMode.CANONICAL_JSON,
    representation_headers: tuple[str, ...] = (
        "content-encoding",
        "if-match",
        "if-none-match",
    ),
    maximum_body_bytes: int = MAX_COMMAND_BODY_BYTES,
) -> PreparedCommand:
    """Collect a bounded body, retain it for parsing, and derive opaque identities."""
    if not isinstance(request, Request):
        raise FastAPIEffectsConfigurationError("Command preparation requires a Starlette request.")
    raw_headers = tuple(request.scope.get("headers", ()))
    key = _one_raw_header(raw_headers, b"idempotency-key", required=True)
    if key is None:  # Defensive: required headers are rejected by _one_raw_header.
        raise FastAPIEffectsConfigurationError("Idempotency-Key is required.")
    selected: list[tuple[str, str]] = []
    normalized_names: set[bytes] = set()
    for configured in representation_headers:
        try:
            name = configured.lower().encode("ascii")
        except (AttributeError, UnicodeEncodeError) as exc:
            raise FastAPIEffectsConfigurationError(
                "Command representation header name is invalid."
            ) from exc
        if not _HEADER_NAME.fullmatch(name) or name in normalized_names:
            raise FastAPIEffectsConfigurationError("Command representation header name is invalid.")
        normalized_names.add(name)
        value = _one_raw_header(raw_headers, name, required=False)
        if value is not None:
            try:
                selected.append((name.decode("ascii"), value.decode("utf-8")))
            except UnicodeDecodeError as exc:
                raise FastAPIEffectsConfigurationError(
                    "Command representation header value is invalid."
                ) from exc
    body = await _bounded_body(request, maximum_body_bytes=maximum_body_bytes)
    content_type = _one_raw_header(raw_headers, b"content-type", required=False)
    media_type: str | None = None
    if content_type is not None:
        try:
            media_type = content_type.decode("ascii").split(";", 1)[0].strip()
        except UnicodeDecodeError as exc:
            raise FastAPIEffectsConfigurationError("Command media type is invalid.") from exc
    path_parameters = {str(name): str(value) for name, value in request.path_params.items()}
    raw_query = request.scope.get("query_string", b"")
    if not isinstance(raw_query, bytes):
        raise FastAPIEffectsConfigurationError("Command query representation is invalid.")
    return PreparedCommand(
        identity=CommandIdentity.from_key(
            tenant_id=principal.tenant_id,
            route_id=route_id,
            method=request.method,
            key=key,
        ),
        fingerprint=fingerprint_request(
            path_parameters=path_parameters,
            raw_query=raw_query,
            headers=selected,
            media_type=media_type,
            body=body,
            mode=body_mode,
            maximum_body_bytes=maximum_body_bytes,
        ),
    )


async def _bounded_body(request: Request, *, maximum_body_bytes: int) -> bytes:
    if not 0 <= maximum_body_bytes <= 16 * 1024 * 1024:
        raise FastAPIEffectsConfigurationError("Command request body limit is invalid.")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError as exc:
            raise FastAPIEffectsConfigurationError("Command Content-Length is invalid.") from exc
        if declared_size < 0 or declared_size > maximum_body_bytes:
            raise FastAPIEffectsConfigurationError("Command request body is oversized.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > maximum_body_bytes:
            raise FastAPIEffectsConfigurationError("Command request body is oversized.")
        chunks.append(chunk)
    body = b"".join(chunks)
    request._body = body  # Starlette's documented body helpers reuse this request cache.
    return body


def _one_raw_header(
    headers: tuple[tuple[bytes, bytes], ...],
    name: bytes,
    *,
    required: bool,
) -> bytes | None:
    values = [value for header, value in headers if header.lower() == name]
    if len(values) > 1 or (required and not values):
        raise FastAPIEffectsConfigurationError(
            "Required command request header is missing or repeated."
        )
    return None if not values else values[0]


__all__ = ["PreparedCommand", "prepare_request"]

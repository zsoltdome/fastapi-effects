"""Bounded replay-safe HTTP response capture and reconstruction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from starlette.responses import Response

from fastapi_effects.errors import FastAPIEffectsConfigurationError

MAX_RESPONSE_BODY_BYTES = 256 * 1024
MAX_RESPONSE_HEADER_BYTES = 16 * 1024
_ALLOWED_MEDIA_TYPES = frozenset({"application/json", "application/problem+json", "text/plain"})
_SAFE_HEADERS = frozenset({"cache-control", "content-language", "etag", "last-modified"})
_UNSAFE_HEADERS = frozenset(
    {
        "authorization",
        "connection",
        "cookie",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "set-cookie",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "www-authenticate",
    }
)


@dataclass(frozen=True, slots=True)
class CapturedResponse:
    status_code: int
    media_type: str
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status_code, int)
            or isinstance(self.status_code, bool)
            or not 200 <= self.status_code <= 599
        ):
            raise FastAPIEffectsConfigurationError("Command response status is not replay-safe.")
        if not isinstance(self.media_type, str):
            raise FastAPIEffectsConfigurationError(
                "Command response media type is not replay-safe."
            )
        media_type = self.media_type.lower().split(";", 1)[0].strip()
        if media_type not in _ALLOWED_MEDIA_TYPES:
            raise FastAPIEffectsConfigurationError(
                "Command response media type is not replay-safe."
            )
        if not isinstance(self.body, bytes) or len(self.body) > MAX_RESPONSE_BODY_BYTES:
            raise FastAPIEffectsConfigurationError("Command response body is oversized.")
        normalized: dict[str, str] = {}
        size = 0
        if not isinstance(self.headers, Mapping):
            raise FastAPIEffectsConfigurationError("Command response headers are invalid.")
        for raw_name, value in self.headers.items():
            if not isinstance(raw_name, str):
                raise FastAPIEffectsConfigurationError(
                    "Command response header is not replay-safe."
                )
            name = raw_name.lower()
            if (
                name in _UNSAFE_HEADERS
                or name not in _SAFE_HEADERS
                or not isinstance(value, str)
                or any(character in value for character in "\r\n\x00")
            ):
                raise FastAPIEffectsConfigurationError(
                    "Command response header is not replay-safe."
                )
            size += len(name.encode()) + len(value.encode())
            normalized[name] = value
        if size > MAX_RESPONSE_HEADER_BYTES:
            raise FastAPIEffectsConfigurationError("Command response headers are oversized.")
        object.__setattr__(self, "media_type", media_type)
        object.__setattr__(self, "headers", MappingProxyType(normalized))

    def to_response(self, *, replayed: bool = False) -> Response:
        headers = dict(self.headers)
        if replayed:
            headers["Idempotency-Replayed"] = "true"
        return Response(
            content=self.body,
            status_code=self.status_code,
            headers=headers,
            media_type=self.media_type,
        )


def capture_response(response: Response) -> CapturedResponse:
    body = getattr(response, "body", None)
    if not isinstance(body, bytes):
        raise FastAPIEffectsConfigurationError("Streaming responses cannot be replayed.")
    media_type = response.media_type
    if media_type is None:
        content_type = response.headers.get("content-type", "")
        media_type = content_type.split(";", 1)[0]
    headers: dict[str, str] = {}
    for name, value in response.headers.items():
        normalized = name.lower()
        if normalized in {"content-type", "content-length"}:
            continue
        if normalized in _UNSAFE_HEADERS:
            raise FastAPIEffectsConfigurationError("Command response contains an unsafe header.")
        headers[name] = value
    return CapturedResponse(
        status_code=response.status_code,
        media_type=media_type,
        body=body,
        headers=headers,
    )


__all__ = [
    "MAX_RESPONSE_BODY_BYTES",
    "MAX_RESPONSE_HEADER_BYTES",
    "CapturedResponse",
    "capture_response",
]

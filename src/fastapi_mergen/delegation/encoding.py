"""Deterministic signed-byte and transport encoding for delegation."""

from __future__ import annotations

import base64
import re

from fastapi_mergen.delegation.models import DelegationClaims
from fastapi_mergen.errors import AuthorizationDenied, MergenConfigurationError
from fastapi_mergen.sqlalchemy.canonical import canonical_json_bytes, strict_json_loads

_PART = re.compile(r"^[A-Za-z0-9_-]+$")
_PREFIX = "mrg1"


def claims_bytes(claims: DelegationClaims) -> bytes:
    return canonical_json_bytes(claims.to_dict(), maximum_bytes=6144)


def encode_token(payload: bytes, signature: bytes) -> str:
    if not isinstance(payload, bytes) or not payload or len(payload) > 6144:
        raise MergenConfigurationError("Delegation payload bytes are invalid.")
    if not isinstance(signature, bytes) or len(signature) != 32:
        raise MergenConfigurationError("Delegation signature bytes are invalid.")
    return f"{_PREFIX}.{_encode(payload)}.{_encode(signature)}"


def decode_token(token: str) -> tuple[DelegationClaims, bytes, bytes]:
    if not isinstance(token, str) or not token or len(token) > 8192:
        raise AuthorizationDenied("Delegation credential was rejected.")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != _PREFIX:
        raise AuthorizationDenied("Delegation credential was rejected.")
    try:
        payload = _decode(parts[1], maximum=6144)
        signature = _decode(parts[2], maximum=32)
        if len(signature) != 32:
            raise ValueError
        parsed = strict_json_loads(payload, maximum_bytes=6144)
        if not isinstance(parsed, dict):
            raise ValueError
        claims = DelegationClaims.from_dict(parsed)
    except (MergenConfigurationError, TypeError, ValueError) as exc:
        raise AuthorizationDenied("Delegation credential was rejected.") from exc
    return claims, payload, signature


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str, *, maximum: int) -> bytes:
    if not value or not _PART.fullmatch(value):
        raise ValueError
    decoded = base64.b64decode(
        value + "=" * (-len(value) % 4),
        altchars=b"-_",
        validate=True,
    )
    if len(decoded) > maximum:
        raise ValueError
    return decoded


__all__ = ["claims_bytes", "decode_token", "encode_token"]

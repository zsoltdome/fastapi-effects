"""Versioned, bounded canonical JSON used at durable trust boundaries."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from fastapi_mergen.errors import MergenConfigurationError

CANONICAL_PAYLOAD_VERSION = 1
DEFAULT_MAX_PAYLOAD_BYTES = 256 * 1024
_PREFIX = b"fastapi-mergen:canonical-json:v1\n"
_MAX_DEPTH = 64
_MAX_CONTAINER_ITEMS = 10_000


def canonical_json_bytes(
    value: object,
    *,
    maximum_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> bytes:
    """Return deterministic UTF-8 JSON after strict semantic validation."""
    if not isinstance(maximum_bytes, int) or isinstance(maximum_bytes, bool) or maximum_bytes < 1:
        raise MergenConfigurationError("Canonical JSON maximum size must be positive.")
    normalized = _normalize(value, path="$", seen=set())
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MergenConfigurationError("Value cannot be represented as canonical JSON.") from exc
    if len(encoded) > maximum_bytes:
        raise MergenConfigurationError("Canonical JSON exceeds the configured byte limit.")
    return encoded


def versioned_canonical_bytes(
    value: object,
    *,
    maximum_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> bytes:
    """Return bytes whose format identity is included in every durable digest."""
    body_limit = maximum_bytes - len(_PREFIX)
    if body_limit < 1:
        raise MergenConfigurationError("Canonical JSON maximum size is too small.")
    return _PREFIX + canonical_json_bytes(value, maximum_bytes=body_limit)


def canonical_sha256(
    value: object,
    *,
    maximum_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> bytes:
    """Hash the format-tagged canonical representation."""
    return hashlib.sha256(versioned_canonical_bytes(value, maximum_bytes=maximum_bytes)).digest()


def strict_json_loads(
    value: bytes | str,
    *,
    maximum_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> object:
    """Parse bounded JSON while rejecting duplicates and non-finite constants."""
    if isinstance(value, str):
        try:
            raw = value.encode("utf-8")
        except UnicodeError as exc:
            raise MergenConfigurationError("JSON input is not valid UTF-8.") from exc
    elif isinstance(value, bytes):
        raw = value
    else:
        raise MergenConfigurationError("JSON input must be bytes or text.")
    if len(raw) > maximum_bytes:
        raise MergenConfigurationError("JSON input exceeds the configured byte limit.")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        semantic_keys: set[str] = set()
        for key, item in pairs:
            semantic = unicodedata.normalize("NFC", key)
            if semantic in semantic_keys:
                raise MergenConfigurationError("JSON object contains duplicate semantic keys.")
            semantic_keys.add(semantic)
            result[key] = item
        return result

    def reject_constant(_value: str) -> None:
        raise MergenConfigurationError("JSON contains a non-finite number.")

    try:
        decoded = raw.decode("utf-8")
        parsed = json.loads(
            decoded,
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except MergenConfigurationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MergenConfigurationError("JSON input is malformed.") from exc
    _normalize(parsed, path="$", seen=set())
    return parsed


def _normalize(value: object, *, path: str, seen: set[int], depth: int = 0) -> object:
    if depth > _MAX_DEPTH:
        raise MergenConfigurationError("Canonical JSON exceeds the nesting limit.")
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="json"), path=path, seen=seen, depth=depth)
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeError as exc:
                raise MergenConfigurationError("Canonical JSON contains invalid text.") from exc
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MergenConfigurationError("Canonical JSON contains a non-finite number.")
        return value
    if isinstance(value, Mapping):
        if len(value) > _MAX_CONTAINER_ITEMS:
            raise MergenConfigurationError("Canonical JSON object has too many members.")
        identity = id(value)
        if identity in seen:
            raise MergenConfigurationError("Canonical JSON contains a reference cycle.")
        seen.add(identity)
        result: dict[str, object] = {}
        semantic_keys: set[str] = set()
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise MergenConfigurationError("Canonical JSON object keys must be strings.")
                semantic = unicodedata.normalize("NFC", key)
                if semantic in semantic_keys:
                    raise MergenConfigurationError(
                        "Canonical JSON object contains duplicate semantic keys."
                    )
                semantic_keys.add(semantic)
                result[key] = _normalize(
                    item,
                    path=f"{path}.{key}",
                    seen=seen,
                    depth=depth + 1,
                )
        finally:
            seen.remove(identity)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > _MAX_CONTAINER_ITEMS:
            raise MergenConfigurationError("Canonical JSON array has too many items.")
        identity = id(value)
        if identity in seen:
            raise MergenConfigurationError("Canonical JSON contains a reference cycle.")
        seen.add(identity)
        try:
            return [
                _normalize(
                    item,
                    path=f"{path}[{index}]",
                    seen=seen,
                    depth=depth + 1,
                )
                for index, item in enumerate(value)
            ]
        finally:
            seen.remove(identity)
    raise MergenConfigurationError(f"Unsupported canonical JSON value at {path}.")


__all__ = [
    "CANONICAL_PAYLOAD_VERSION",
    "DEFAULT_MAX_PAYLOAD_BYTES",
    "canonical_json_bytes",
    "canonical_sha256",
    "strict_json_loads",
    "versioned_canonical_bytes",
]

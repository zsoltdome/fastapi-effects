"""Bounded evidence normalization and secret-field rejection."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SENSITIVE = re.compile(
    r"(^|[_-])(authorization|cookie|password|passwd|secret|token|signature|private[_-]?key|"
    r"api[_-]?key|refresh[_-]?token|access[_-]?token|session)([_-]|$)",
    re.IGNORECASE,
)
_SAFE_SENSITIVE_NAMES = frozenset({"key_id", "credential_ref", "secret_set_id", "token_id"})
_MAX_DEPTH = 8
_MAX_ITEMS = 128
_MAX_STRING = 2048
_MAX_KEY = 128

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def clean_text(value: str, *, maximum: int = _MAX_STRING) -> str:
    """Remove unsafe controls and enforce a deterministic maximum length."""

    value = _CONTROL.sub(" ", value)
    return value[:maximum]


def is_sensitive_key(key: str) -> bool:
    """Return whether a mapping key could hold reusable credential material."""

    normalized = key.lower()
    return normalized not in _SAFE_SENSITIVE_NAMES and _SENSITIVE.search(normalized) is not None


def reject_sensitive_keys(value: object, *, path: str = "metadata", depth: int = 0) -> None:
    """Reject manifest metadata that would require redaction to publish safely."""

    if depth > _MAX_DEPTH:
        raise MergenConfigurationError(f"{path} exceeds the maximum nesting depth.")
    if isinstance(value, Mapping):
        if len(value) > _MAX_ITEMS:
            raise MergenConfigurationError(f"{path} contains too many entries.")
        for raw_key, item in value.items():
            if not isinstance(raw_key, str) or not raw_key or len(raw_key) > _MAX_KEY:
                raise MergenConfigurationError(f"{path} contains an invalid key.")
            if is_sensitive_key(raw_key):
                raise MergenConfigurationError(f"{path} contains a sensitive field name.")
            reject_sensitive_keys(item, path=f"{path}.{raw_key}", depth=depth + 1)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > _MAX_ITEMS:
            raise MergenConfigurationError(f"{path} contains too many entries.")
        for index, item in enumerate(value):
            reject_sensitive_keys(item, path=f"{path}[{index}]", depth=depth + 1)


def safe_json(value: object, *, depth: int = 0) -> JsonValue:
    """Convert arbitrary evidence into a bounded, credential-safe JSON value."""

    if depth > _MAX_DEPTH:
        return "<maximum-depth>"
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else "<non-finite>"
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<{len(value)} bytes>"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID | Path):
        return str(value)
    if isinstance(value, Enum):
        return safe_json(value.value, depth=depth + 1)
    if is_dataclass(value) and not isinstance(value, type):
        return safe_json(asdict(value), depth=depth + 1)
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        entries = list(value.items())[:_MAX_ITEMS]
        for raw_key, item in entries:
            key = clean_text(str(raw_key), maximum=_MAX_KEY)
            result[key] = (
                "<redacted>" if is_sensitive_key(key) else safe_json(item, depth=depth + 1)
            )
        if len(value) > _MAX_ITEMS:
            result["<truncated>"] = len(value) - _MAX_ITEMS
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = [safe_json(item, depth=depth + 1) for item in list(value)[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            items.append(f"<{len(value) - _MAX_ITEMS} more items>")
        return items
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def scan_for_secret_values(value: object, canaries: Sequence[str]) -> tuple[str, ...]:
    """Return secret canaries visible in normalized report evidence."""

    serialized = repr(safe_json(value))
    return tuple(canary for canary in canaries if canary and canary in serialized)

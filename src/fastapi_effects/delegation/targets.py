"""Fail-closed HTTP method and exact target-path canonicalization."""

from __future__ import annotations

import re

from fastapi_effects.errors import FastAPIEffectsConfigurationError

_METHOD = re.compile(r"^[A-Z][A-Z0-9!#$%&'*+.^_`|~-]{0,31}$")
_HEX = frozenset("0123456789abcdefABCDEF")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def canonical_method(value: str) -> str:
    if not isinstance(value, str) or not _METHOD.fullmatch(value):
        raise FastAPIEffectsConfigurationError("Delegation HTTP method is invalid.")
    return value


def canonical_target_path(value: str) -> str:
    """Return one exact ASCII path while rejecting normalization ambiguity."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "?" in value
        or "#" in value
        or _CONTROL.search(value) is not None
    ):
        raise FastAPIEffectsConfigurationError("Delegation target path is invalid.")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise FastAPIEffectsConfigurationError(
            "Delegation target path must use an ASCII URI representation."
        ) from exc

    normalized: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "%":
            normalized.append(character)
            index += 1
            continue
        if index + 2 >= len(value) or value[index + 1] not in _HEX or value[index + 2] not in _HEX:
            raise FastAPIEffectsConfigurationError(
                "Delegation target has malformed percent encoding."
            )
        octet = int(value[index + 1 : index + 3], 16)
        decoded = chr(octet)
        if decoded in {"/", "\\", "%"} or octet < 0x20 or octet == 0x7F:
            raise FastAPIEffectsConfigurationError(
                "Delegation target contains an unsafe encoded octet."
            )
        if decoded in _UNRESERVED:
            normalized.append(decoded)
        else:
            normalized.append(f"%{octet:02X}")
        index += 3
    result = "".join(normalized)
    segments = result.split("/")[1:]
    if any(segment in {"", ".", ".."} for segment in segments):
        raise FastAPIEffectsConfigurationError(
            "Delegation target path contains an ambiguous segment."
        )
    return result


__all__ = ["canonical_method", "canonical_target_path"]

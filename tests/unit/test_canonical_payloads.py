from __future__ import annotations

import math

import pytest

from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.sqlalchemy.canonical import (
    canonical_json_bytes,
    canonical_sha256,
    strict_json_loads,
    versioned_canonical_bytes,
)


def test_canonical_payload_order_and_digest_are_stable() -> None:
    left = {"currency": "EUR", "amount": 12.5, "items": [1, True, None]}
    right = {"items": [1, True, None], "amount": 12.5, "currency": "EUR"}

    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert versioned_canonical_bytes(left).startswith(b"fastapi_effects:canonical-json:v1\n")
    assert canonical_sha256(left) == canonical_sha256(right)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, object(), {1: "bad"}])
def test_canonical_payload_rejects_unsupported_values(value: object) -> None:
    with pytest.raises(FastAPIEffectsConfigurationError):
        canonical_json_bytes({"value": value})


def test_strict_json_rejects_duplicate_semantic_keys_and_bounds() -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="duplicate semantic"):
        strict_json_loads('{"é":1,"é":2}')
    with pytest.raises(FastAPIEffectsConfigurationError, match="byte limit"):
        canonical_json_bytes({"value": "oversized"}, maximum_bytes=4)

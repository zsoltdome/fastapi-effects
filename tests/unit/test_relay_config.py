from __future__ import annotations

import math
from typing import Any

import pytest

from fastapi_effects.postgres.relay import RelayConfig

_TIMING_FIELDS = (
    ("poll_interval_seconds", 60),
    ("control_plane_timeout_seconds", 300),
    ("finalization_timeout_seconds", 300),
    ("shutdown_grace_seconds", 300),
)


@pytest.mark.parametrize(("field", "maximum"), _TIMING_FIELDS)
@pytest.mark.parametrize(
    "invalid",
    [
        math.nan,
        math.inf,
        -math.inf,
        True,
        False,
        "1",
        None,
        0,
        -1,
        pytest.param(10**10_000, id="oversized-integer"),
    ],
)
def test_relay_timing_fields_reject_invalid_values(
    field: str,
    maximum: int,
    invalid: object,
) -> None:
    del maximum
    values: dict[str, Any] = {field: invalid}

    with pytest.raises(ValueError, match=r"must be in \(0, (60|300)\]"):
        RelayConfig(**values)


@pytest.mark.parametrize(("field", "maximum"), _TIMING_FIELDS)
@pytest.mark.parametrize("kind", [int, float])
def test_relay_timing_fields_accept_representative_and_exact_upper_bounds(
    field: str,
    maximum: int,
    kind: type[int] | type[float],
) -> None:
    representative: dict[str, Any] = {field: kind(1)}
    upper: dict[str, Any] = {field: kind(maximum)}

    assert getattr(RelayConfig(**representative), field) == kind(1)
    assert getattr(RelayConfig(**upper), field) == kind(maximum)


def test_relay_timing_defaults_are_unchanged() -> None:
    config = RelayConfig()

    assert config.poll_interval_seconds == 1.0
    assert config.control_plane_timeout_seconds == 10.0
    assert config.finalization_timeout_seconds == 10.0
    assert config.shutdown_grace_seconds == 30.0

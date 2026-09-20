from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.observability.events import RuntimeEvent, RuntimeEventKind
from fastapi_effects.observability.protocols import NoOpEventSink


def test_runtime_events_reject_payload_secret_and_unbounded_attributes() -> None:
    now = datetime.now(UTC)
    for key in ("payload", "http.body", "credential_ref", "api_key"):
        with pytest.raises(FastAPIEffectsConfigurationError, match="unsafe"):
            RuntimeEvent(RuntimeEventKind.PUBLISHED, now, {key: "canary"})
    with pytest.raises(FastAPIEffectsConfigurationError, match="finite"):
        RuntimeEvent(RuntimeEventKind.ATTEMPTED, now, {"duration": math.inf})
    with pytest.raises(FastAPIEffectsConfigurationError, match="oversized"):
        RuntimeEvent(RuntimeEventKind.DEAD, now, {"failure.code": "x" * 257})


def test_noop_observability_has_no_optional_dependency_behavior() -> None:
    event = RuntimeEvent(
        RuntimeEventKind.SUCCEEDED,
        datetime.now(UTC),
        {"attempt.number": 1},
    )
    assert NoOpEventSink().record(event) is None

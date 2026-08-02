from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fastapi_mergen.core.delivery import (
    AttemptOutcome,
    AttemptRecord,
    DeliveryRecord,
    DeliveryState,
)
from fastapi_mergen.errors import MergenConfigurationError

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _delivery(**changes: object) -> DeliveryRecord:
    values: dict[str, object] = {
        "delivery_id": uuid4(),
        "tenant_id": uuid4(),
        "event_id": uuid4(),
        "route_key": "invoice.render",
        "route_version": 1,
        "destination_kind": "handler",
        "destination_key": "invoice.render",
        "route_snapshot": b"{}",
        "state": DeliveryState.PENDING,
        "attempts_started": 0,
        "created_at": NOW,
        "updated_at": NOW,
        "next_attempt_at": NOW,
    }
    values.update(changes)
    return DeliveryRecord(**values)  # type: ignore[arg-type]


def test_delivery_is_immutable_and_lease_state_is_coherent() -> None:
    delivery = _delivery()
    with pytest.raises(FrozenInstanceError):
        delivery.state = DeliveryState.DEAD  # type: ignore[misc]
    with pytest.raises(MergenConfigurationError, match="lease token"):
        _delivery(state=DeliveryState.LEASED)
    with pytest.raises(MergenConfigurationError, match="Only a leased"):
        _delivery(lease_token=uuid4(), lease_expires_at=NOW + timedelta(seconds=30))


def test_replay_requires_new_identity_and_accountable_metadata() -> None:
    original = _delivery()
    replay = _delivery(
        replay_of=original.delivery_id,
        replay_actor="operator:42",
        replay_reason="operator-approved",
    )
    assert replay.delivery_id != original.delivery_id
    with pytest.raises(MergenConfigurationError, match="Replay"):
        _delivery(replay_of=original.delivery_id)


def test_attempt_outcomes_reject_impossible_failure_combinations() -> None:
    identities = {
        "attempt_id": uuid4(),
        "tenant_id": uuid4(),
        "delivery_id": uuid4(),
        "attempt_number": 1,
        "lease_token": uuid4(),
        "started_at": NOW,
    }
    started = AttemptRecord(outcome=AttemptOutcome.STARTED, **identities)
    assert started.finished_at is None
    with pytest.raises(MergenConfigurationError, match="requires bounded failure"):
        AttemptRecord(
            outcome=AttemptOutcome.RETRYABLE,
            finished_at=NOW + timedelta(seconds=1),
            **identities,
        )
    succeeded = AttemptRecord(
        outcome=AttemptOutcome.SUCCEEDED,
        finished_at=NOW + timedelta(seconds=1),
        **identities,
    )
    assert succeeded.failure_code is None
    failed = AttemptRecord(
        outcome=AttemptOutcome.TERMINAL,
        finished_at=NOW + timedelta(seconds=1),
        failure_code="handler.denied",
        failure_summary="Handler denied the effect.",
        **identities,
    )
    assert failed.outcome is AttemptOutcome.TERMINAL

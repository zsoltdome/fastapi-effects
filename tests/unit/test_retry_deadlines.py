from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fastapi_effects.core.retry import (
    RetryPolicy,
    attempt_deadline,
    delivery_deadline,
    remaining_attempt_seconds,
)
from fastapi_effects.webhooks.classification import parse_retry_after

CREATED = datetime(2026, 9, 7, 12, tzinfo=UTC)
POLICY = RetryPolicy(
    name="deadline-boundaries",
    maximum_elapsed_seconds=30,
    maximum_delay_seconds=30,
    handler_timeout_seconds=10,
    lease_duration_seconds=20,
)


def test_latest_finish_deadlines_are_exact_at_the_boundary() -> None:
    started = CREATED + timedelta(seconds=5)
    lease_expires = CREATED + timedelta(seconds=25)
    deadline = attempt_deadline(
        policy=POLICY,
        delivery_created_at=CREATED,
        attempt_started_at=started,
        lease_expires_at=lease_expires,
    )

    assert delivery_deadline(policy=POLICY, created_at=CREATED) == CREATED + timedelta(seconds=30)
    assert deadline == CREATED + timedelta(seconds=15)
    assert remaining_attempt_seconds(
        policy=POLICY,
        delivery_created_at=CREATED,
        attempt_started_at=started,
        lease_expires_at=lease_expires,
        now=deadline - timedelta(microseconds=1),
    ) == pytest.approx(0.000001)
    assert (
        remaining_attempt_seconds(
            policy=POLICY,
            delivery_created_at=CREATED,
            attempt_started_at=started,
            lease_expires_at=lease_expires,
            now=deadline,
        )
        == 0
    )
    assert (
        remaining_attempt_seconds(
            policy=POLICY,
            delivery_created_at=CREATED,
            attempt_started_at=started,
            lease_expires_at=lease_expires,
            now=deadline + timedelta(microseconds=1),
        )
        == 0
    )


def test_retry_after_cannot_cross_or_reopen_the_delivery_deadline() -> None:
    deadline = delivery_deadline(policy=POLICY, created_at=CREATED)
    assert parse_retry_after(
        "999",
        now=deadline - timedelta(seconds=1),
        maximum=timedelta(seconds=30),
        deadline=deadline,
    ) == timedelta(seconds=1)
    assert parse_retry_after(
        "999",
        now=deadline,
        maximum=timedelta(seconds=30),
        deadline=deadline,
    ) == timedelta(0)
    assert parse_retry_after(
        "999",
        now=deadline + timedelta(seconds=1),
        maximum=timedelta(seconds=30),
        deadline=deadline,
    ) == timedelta(0)

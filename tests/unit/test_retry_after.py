from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi_effects.webhooks.classification import parse_retry_after


def test_retry_after_delta_and_date_are_clamped() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_retry_after("12", now=now, maximum=timedelta(seconds=30)) == timedelta(seconds=12)
    assert parse_retry_after("999", now=now, maximum=timedelta(seconds=30)) == timedelta(seconds=30)
    assert parse_retry_after(
        "Thu, 01 Jan 2026 00:00:20 GMT",
        now=now,
        maximum=timedelta(seconds=30),
        deadline=now + timedelta(seconds=7),
    ) == timedelta(seconds=7)
    assert parse_retry_after("receiver-controlled", now=now, maximum=timedelta(1)) is None

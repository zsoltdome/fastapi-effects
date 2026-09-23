from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from fastapi_effects import FastAPIEffectsConfigurationError, Principal, RetryPolicy
from fastapi_effects.executors.taskiq.store import TaskiqHandoffStore
from fastapi_effects.executors.taskiq.worker import TaskiqWorkerBridge
from fastapi_effects.webhooks.http11 import ResponseLimits
from fastapi_effects.webhooks.operations import WebhookOperations
from fastapi_effects.webhooks.transport import TransportLimits


class _IdleSession:
    def in_transaction(self) -> bool:
        return False


class _Sessions:
    pass


class _Executor:
    pass


@pytest.mark.parametrize(
    "field",
    [
        "base_delay_seconds",
        "maximum_delay_seconds",
        "handler_timeout_seconds",
        "lease_duration_seconds",
    ],
)
@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True, "1", None])
def test_retry_policy_finite_number_checks_remain_fail_closed(
    field: str,
    invalid: object,
) -> None:
    values: dict[str, Any] = {"name": "numeric.inventory", field: invalid}

    with pytest.raises(FastAPIEffectsConfigurationError):
        RetryPolicy(**values)


@pytest.mark.parametrize(
    "field",
    ["connect_timeout_seconds", "write_timeout_seconds", "total_timeout_seconds"],
)
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
        301,
        pytest.param(10**10_000, id="oversized-integer"),
    ],
)
def test_webhook_transport_timeouts_reject_non_finite_and_invalid_values(
    field: str,
    invalid: object,
) -> None:
    values: dict[str, Any] = {field: invalid}

    with pytest.raises(ValueError, match="Webhook"):
        TransportLimits(**values)


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
        301,
        pytest.param(10**10_000, id="oversized-integer"),
    ],
)
def test_webhook_response_timeout_rejects_non_finite_and_invalid_values(
    invalid: object,
) -> None:
    with pytest.raises(ValueError, match="HTTP read timeout"):
        ResponseLimits(read_timeout_seconds=invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [1, 1.0, 300, 300.0])
def test_webhook_timeout_boundaries_remain_valid(value: int | float) -> None:
    transport = TransportLimits(
        connect_timeout_seconds=value,
        write_timeout_seconds=value,
        total_timeout_seconds=value,
    )
    response = ResponseLimits(read_timeout_seconds=value)

    assert transport.total_timeout_seconds == value
    assert response.read_timeout_seconds == value


def test_webhook_byte_and_count_limits_reject_boolean_values() -> None:
    with pytest.raises(ValueError, match="maximum request size"):
        TransportLimits(maximum_request_bytes=True)
    with pytest.raises(ValueError, match="byte/count bounds"):
        ResponseLimits(maximum_body_bytes=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [True, False, 1.0, "1", None, 0, -1, 10_001])
async def test_webhook_retention_batch_rejects_non_integer_and_out_of_range_values(
    invalid: object,
) -> None:
    operations = object.__new__(WebhookOperations)
    principal = Principal(
        tenant_id=uuid4(),
        subject_id="numeric:inventory",
        scopes=frozenset({"webhooks:manage"}),
    )

    with pytest.raises(FastAPIEffectsConfigurationError, match="batch size"):
        await operations.retain(
            _IdleSession(),  # type: ignore[arg-type]
            principal=principal,
            before=datetime.now(UTC),
            batch_size=invalid,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("execution_timeout", True),
        ("execution_timeout", timedelta(0)),
        ("execution_timeout", timedelta(hours=1, microseconds=1)),
        ("control_plane_timeout", "10"),
        ("control_plane_timeout", timedelta(0)),
        ("control_plane_timeout", timedelta(minutes=5, microseconds=1)),
    ],
)
def test_taskiq_worker_budgets_reject_wrong_types_and_out_of_range_values(
    field: str,
    invalid: object,
) -> None:
    values: dict[str, object] = {
        "sessions": _Sessions(),
        "executor": _Executor(),
        field: invalid,
    }

    with pytest.raises(FastAPIEffectsConfigurationError, match="operation budgets"):
        TaskiqWorkerBridge(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("batch_size", True),
        ("batch_size", "100"),
        ("batch_size", 0),
        ("batch_size", 10_001),
        ("enqueue_timeout", True),
        ("enqueue_timeout", timedelta(0)),
    ],
)
async def test_taskiq_recovery_bounds_reject_wrong_types_and_invalid_values(
    field: str,
    invalid: object,
) -> None:
    values: dict[str, object] = {
        "now": datetime.now(UTC),
        "enqueue_timeout": timedelta(minutes=5),
        "batch_size": 100,
        field: invalid,
    }

    with pytest.raises(FastAPIEffectsConfigurationError, match="Taskiq"):
        await TaskiqHandoffStore().recover_expired(
            _IdleSession(),  # type: ignore[arg-type]
            **values,  # type: ignore[arg-type]
        )

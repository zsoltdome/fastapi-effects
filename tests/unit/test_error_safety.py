from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest

from fastapi_mergen import (
    DedupeConflict,
    LeaseLost,
    MergenConfigurationError,
    PermanentDeliveryError,
    RetryableDeliveryError,
    SchemaRevisionMismatch,
)


def test_public_errors_exclude_payloads_from_string_and_repr() -> None:
    secret_payload = "canary-payload-never-log"
    conflict = DedupeConflict(namespace="invoice-create", key="request-1")
    assert secret_payload not in str(conflict)
    assert "request-1" not in str(conflict)

    retryable = RetryableDeliveryError(code="temporary", summary=secret_payload + "x" * 900)
    permanent = PermanentDeliveryError(code="remote-rejected", summary=secret_payload)
    assert len(retryable.summary) == 512
    assert secret_payload not in str(retryable)
    assert secret_payload not in repr(retryable)
    assert secret_payload not in str(permanent)
    assert secret_payload not in repr(permanent)

    delivery_id = uuid4()
    assert str(delivery_id) in str(LeaseLost(delivery_id=delivery_id))


def test_public_error_fields_reject_unsafe_runtime_values() -> None:
    with pytest.raises(MergenConfigurationError, match="error code"):
        RetryableDeliveryError(code="bad\ncode", summary="safe")
    with pytest.raises(MergenConfigurationError, match="dedupe key"):
        DedupeConflict(namespace="invoice-create", key="bad\nkey")
    with pytest.raises(MergenConfigurationError, match="UUID"):
        LeaseLost(delivery_id=cast(Any, "not-a-uuid"))
    with pytest.raises(MergenConfigurationError, match="non-negative"):
        SchemaRevisionMismatch(component="route-snapshot", expected=1, actual=-1)

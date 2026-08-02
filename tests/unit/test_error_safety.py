from __future__ import annotations

import re
from typing import Any, cast
from uuid import uuid4

import pytest

import fastapi_mergen
from fastapi_mergen import (
    AuthenticationRequired,
    CommandConflict,
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


def test_public_errors_expose_stable_machine_codes() -> None:
    assert AuthenticationRequired.error_code == "mergen.authentication_required"
    assert CommandConflict.error_code == "mergen.command_conflict"
    assert RetryableDeliveryError.error_code == "mergen.delivery_retryable"
    assert SchemaRevisionMismatch.error_code == "mergen.schema_revision_mismatch"
    values = (getattr(fastapi_mergen, name) for name in fastapi_mergen.__all__)
    error_types = [
        value
        for value in values
        if isinstance(value, type) and issubclass(value, fastapi_mergen.MergenError)
    ]
    codes = [error_type.error_code for error_type in error_types]
    assert len(codes) == len(set(codes))
    assert all(re.fullmatch(r"mergen\.[a-z_]+", code) for code in codes)

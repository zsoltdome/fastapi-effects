from uuid import uuid4

from fastapi_mergen import DedupeConflict, LeaseLost, RetryableDeliveryError


def test_public_errors_exclude_payloads() -> None:
    secret_payload = "canary-payload-never-log"
    conflict = DedupeConflict(namespace="invoice-create", key="request-1")
    assert secret_payload not in str(conflict)
    assert "request-1" not in str(conflict)

    retryable = RetryableDeliveryError(code="temporary", summary="x" * 900)
    assert len(retryable.summary) == 512
    assert secret_payload not in str(retryable)

    delivery_id = uuid4()
    assert str(delivery_id) in str(LeaseLost(delivery_id=delivery_id))

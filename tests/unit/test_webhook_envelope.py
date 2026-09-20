from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi_effects import Principal
from fastapi_effects.core.event import EventRecord
from fastapi_effects.sqlalchemy.canonical import canonical_sha256, versioned_canonical_bytes
from fastapi_effects.webhooks.serializer import serialize_webhook_envelope


def test_envelope_is_stable_across_automatic_attempts() -> None:
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    event_id = UUID("22222222-2222-4222-8222-222222222222")
    delivery_id = UUID("33333333-3333-4333-8333-333333333333")
    occurred_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    data = {"amount": 42, "invoice_id": "inv-1"}
    event = EventRecord(
        event_id=event_id,
        tenant_id=tenant_id,
        event_type="invoice.created",
        event_version=1,
        canonical_version=1,
        payload_canonical=versioned_canonical_bytes(data),
        payload_sha256=canonical_sha256(data),
        principal=Principal(tenant_id=tenant_id, subject_id="user:test").to_envelope(),
        occurred_at=occurred_at,
        created_at=occurred_at,
    )

    first = serialize_webhook_envelope(delivery_id=delivery_id, event=event)
    second = serialize_webhook_envelope(delivery_id=delivery_id, event=event)

    assert first == second
    assert json.loads(first) == {
        "data": data,
        "event_id": str(event_id),
        "event_type": "invoice.created",
        "event_version": 1,
        "message_id": f"msg_{delivery_id.hex}",
        "occurred_at": occurred_at.isoformat(),
        "tenant_id": str(tenant_id),
    }

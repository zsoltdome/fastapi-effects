"""Deterministic webhook wire envelopes."""

from __future__ import annotations

from uuid import UUID

from fastapi_effects.core.event import EventRecord
from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.sqlalchemy.canonical import canonical_json_bytes, strict_json_loads

_CANONICAL_PREFIX = b"fastapi_effects:canonical-json:v1\n"


def webhook_message_id(delivery_id: UUID) -> str:
    """Use delivery identity for retries and a new identity for manual replay."""
    if not isinstance(delivery_id, UUID):
        raise FastAPIEffectsConfigurationError("Webhook delivery identity must be a UUID.")
    return f"msg_{delivery_id.hex}"


def serialize_webhook_envelope(
    *,
    delivery_id: UUID,
    event: EventRecord,
) -> bytes:
    """Serialize one stable body whose exact bytes are signed and sent."""
    if not event.payload_canonical.startswith(_CANONICAL_PREFIX):
        raise FastAPIEffectsConfigurationError("Webhook event payload format is unsupported.")
    data = strict_json_loads(event.payload_canonical[len(_CANONICAL_PREFIX) :])
    return canonical_json_bytes(
        {
            "data": data,
            "event_id": str(event.event_id),
            "event_type": event.event_type,
            "event_version": event.event_version,
            "message_id": webhook_message_id(delivery_id),
            "occurred_at": event.occurred_at.isoformat(),
            "tenant_id": str(event.tenant_id),
        }
    )


__all__ = ["serialize_webhook_envelope", "webhook_message_id"]

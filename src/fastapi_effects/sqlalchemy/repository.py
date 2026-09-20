"""Async SQLAlchemy persistence with detached domain return values."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_effects.core.delivery import (
    AttemptOutcome,
    AttemptRecord,
    DeliveryRecord,
    DeliveryState,
)
from fastapi_effects.core.event import Event, EventRecord
from fastapi_effects.core.identity import DedupeIdentity
from fastapi_effects.core.principal import Principal, PrincipalEnvelope
from fastapi_effects.core.protocols import UUIDGenerator
from fastapi_effects.core.routing import RouteSpecification
from fastapi_effects.errors import DedupeConflict, FastAPIEffectsConfigurationError
from fastapi_effects.sqlalchemy.canonical import (
    CANONICAL_PAYLOAD_VERSION,
    canonical_json_bytes,
    versioned_canonical_bytes,
)
from fastapi_effects.sqlalchemy.models import AttemptRow, DeliveryRow, EventRow


class RuntimeRepository:
    """Operate only inside a caller-owned transaction."""

    async def publish(
        self,
        *,
        session: AsyncSession,
        principal: Principal,
        event: Event[object],
        routes: Sequence[RouteSpecification],
        now: datetime,
        uuid_source: UUIDGenerator,
        dedupe_identity: DedupeIdentity | None,
    ) -> EventRecord:
        payload_body = canonical_json_bytes(event.data)
        payload_canonical = versioned_canonical_bytes(event.data)
        import hashlib

        payload_sha256 = hashlib.sha256(payload_canonical).digest()
        event_id = uuid_source.new_uuid()
        values = {
            "tenant_id": principal.tenant_id,
            "event_id": event_id,
            "event_type": event.type,
            "event_version": event.version,
            "canonical_version": CANONICAL_PAYLOAD_VERSION,
            "payload": json.loads(payload_body),
            "payload_canonical": payload_canonical,
            "payload_sha256": payload_sha256,
            "principal": principal.to_envelope().to_dict(),
            "occurred_at": event.occurred_at,
            "created_at": now,
            "correlation_id": event.correlation_id,
            "causation_id": event.causation_id,
            "traceparent": event.traceparent,
            "tracestate": event.tracestate,
            "dedupe_namespace": (None if dedupe_identity is None else dedupe_identity.namespace),
            "dedupe_key": None if dedupe_identity is None else dedupe_identity.key,
        }
        statement = pg_insert(EventRow).values(**values)
        if dedupe_identity is not None:
            statement = statement.on_conflict_do_nothing(
                index_elements=(
                    EventRow.tenant_id,
                    EventRow.dedupe_namespace,
                    EventRow.dedupe_key,
                ),
                index_where=EventRow.dedupe_namespace.is_not(None),
            )
        result = await session.execute(statement.returning(EventRow))
        inserted = result.scalar_one_or_none()
        if inserted is None:
            if dedupe_identity is None:
                raise FastAPIEffectsConfigurationError(
                    "Event insertion returned no durable record."
                )
            existing = await self._event_for_dedupe(
                session=session,
                tenant_id=principal.tenant_id,
                identity=dedupe_identity,
            )
            if (
                existing.event_type != event.type
                or existing.event_version != event.version
                or existing.payload_sha256 != payload_sha256
            ):
                raise DedupeConflict(
                    namespace=dedupe_identity.namespace,
                    key=dedupe_identity.key,
                )
            return event_from_row(existing)

        delivery_rows = [
            DeliveryRow(
                tenant_id=principal.tenant_id,
                delivery_id=uuid_source.new_uuid(),
                event_id=event_id,
                route_key=route.route_key,
                route_version=route.version,
                destination_kind=route.destination_kind,
                destination_key=route.destination_key,
                route_snapshot=route.to_snapshot(),
                route_snapshot_bytes=route.snapshot_bytes(),
                state=DeliveryState.PENDING.value,
                attempts_started=0,
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
            for route in routes
        ]
        session.add_all(delivery_rows)
        await session.flush()
        return event_from_row(inserted)

    async def event_for_id(
        self,
        *,
        session: AsyncSession,
        tenant_id: object,
        event_id: object,
    ) -> EventRecord | None:
        row = await session.scalar(
            select(EventRow).where(
                EventRow.tenant_id == tenant_id,
                EventRow.event_id == event_id,
            )
        )
        return None if row is None else event_from_row(row)

    async def delivery_for_id(
        self,
        *,
        session: AsyncSession,
        tenant_id: object,
        delivery_id: object,
    ) -> DeliveryRecord | None:
        row = await session.scalar(
            select(DeliveryRow).where(
                DeliveryRow.tenant_id == tenant_id,
                DeliveryRow.delivery_id == delivery_id,
            )
        )
        return None if row is None else delivery_from_row(row)

    async def _event_for_dedupe(
        self,
        *,
        session: AsyncSession,
        tenant_id: object,
        identity: DedupeIdentity,
    ) -> EventRow:
        query: Select[tuple[EventRow]] = select(EventRow).where(
            EventRow.tenant_id == tenant_id,
            EventRow.dedupe_namespace == identity.namespace,
            EventRow.dedupe_key == identity.key,
        )
        row = await session.scalar(query)
        if row is None:
            raise FastAPIEffectsConfigurationError(
                "Concurrent dedupe resolution produced no event."
            )
        return row


def event_from_row(row: EventRow) -> EventRecord:
    return EventRecord(
        event_id=row.event_id,
        tenant_id=row.tenant_id,
        event_type=row.event_type,
        event_version=row.event_version,
        canonical_version=row.canonical_version,
        payload_canonical=bytes(row.payload_canonical),
        payload_sha256=bytes(row.payload_sha256),
        principal=PrincipalEnvelope.from_dict(row.principal),
        occurred_at=row.occurred_at,
        created_at=row.created_at,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        traceparent=row.traceparent,
        tracestate=row.tracestate,
        dedupe_namespace=row.dedupe_namespace,
        dedupe_key=row.dedupe_key,
    )


def delivery_from_row(row: DeliveryRow) -> DeliveryRecord:
    return DeliveryRecord(
        delivery_id=row.delivery_id,
        tenant_id=row.tenant_id,
        event_id=row.event_id,
        route_key=row.route_key,
        route_version=row.route_version,
        destination_kind=row.destination_kind,
        destination_key=row.destination_key,
        route_snapshot=bytes(row.route_snapshot_bytes),
        state=DeliveryState(row.state),
        attempts_started=row.attempts_started,
        created_at=row.created_at,
        updated_at=row.updated_at,
        next_attempt_at=row.next_attempt_at,
        lease_token=row.lease_token,
        lease_expires_at=row.lease_expires_at,
        replay_of=row.replay_of,
        replay_actor=row.replay_actor,
        replay_reason=row.replay_reason,
    )


def attempt_from_row(row: AttemptRow) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=row.attempt_id,
        tenant_id=row.tenant_id,
        delivery_id=row.delivery_id,
        attempt_number=row.attempt_number,
        lease_token=row.lease_token,
        outcome=AttemptOutcome(row.outcome),
        started_at=row.started_at,
        finished_at=row.finished_at,
        failure_code=row.failure_code,
        failure_summary=row.failure_summary,
    )


__all__ = [
    "RuntimeRepository",
    "attempt_from_row",
    "delivery_from_row",
    "event_from_row",
]

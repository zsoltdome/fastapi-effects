"""Short claim transactions, lease fencing, and crash reconciliation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.core.delivery import (
    AttemptOutcome,
    AttemptRecord,
    DeliveryRecord,
    DeliveryState,
)
from fastapi_mergen.core.event import EventRecord
from fastapi_mergen.core.identity import UUIDSource
from fastapi_mergen.core.protocols import RandomSource, UUIDGenerator
from fastapi_mergen.core.retry import RetryPolicy
from fastapi_mergen.core.runtime import SystemRandom
from fastapi_mergen.errors import (
    LeaseLost,
    MergenConfigurationError,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_mergen.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_mergen.observability.protocols import EventSink, NoOpEventSink, record_safely
from fastapi_mergen.sqlalchemy.models import AttemptRow, DeliveryRow, EventRow
from fastapi_mergen.sqlalchemy.repository import attempt_from_row, delivery_from_row, event_from_row


@dataclass(frozen=True, slots=True)
class ClaimedDelivery:
    event: EventRecord
    delivery: DeliveryRecord
    attempt: AttemptRecord
    route_snapshot: dict[str, Any]

    @property
    def lease_token(self) -> UUID:
        return self.attempt.lease_token


class LeaseRepository:
    def __init__(
        self,
        *,
        uuid_source: UUIDGenerator | None = None,
        random_source: RandomSource | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self._uuid_source = uuid_source or UUIDSource()
        self._random_source = random_source or SystemRandom()
        self._event_sink = event_sink or NoOpEventSink()

    async def claim(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        batch_size: int = 50,
        per_tenant: int = 5,
    ) -> tuple[ClaimedDelivery, ...]:
        _require_idle(session)
        _positive("batch_size", batch_size)
        _positive("per_tenant", per_tenant)
        claimed: list[ClaimedDelivery] = []
        async with session.begin():
            tenant_rank = func.row_number().over(
                partition_by=DeliveryRow.tenant_id,
                order_by=(DeliveryRow.next_attempt_at, DeliveryRow.created_at),
            )
            ranked = (
                select(
                    DeliveryRow.tenant_id.label("tenant_id"),
                    DeliveryRow.delivery_id.label("delivery_id"),
                    tenant_rank.label("tenant_rank"),
                )
                .where(
                    DeliveryRow.state.in_(
                        (DeliveryState.PENDING.value, DeliveryState.RETRY_WAIT.value)
                    ),
                    DeliveryRow.next_attempt_at <= now,
                )
                .cte("ranked_claimable_deliveries")
            )
            candidates = (
                await session.scalars(
                    select(DeliveryRow)
                    .join(
                        ranked,
                        (ranked.c.tenant_id == DeliveryRow.tenant_id)
                        & (ranked.c.delivery_id == DeliveryRow.delivery_id),
                    )
                    .where(ranked.c.tenant_rank <= per_tenant)
                    .order_by(
                        DeliveryRow.next_attempt_at,
                        DeliveryRow.created_at,
                        DeliveryRow.tenant_id,
                    )
                    .limit(batch_size)
                    .with_for_update(of=DeliveryRow, skip_locked=True)
                )
            ).all()
            counts: Counter[UUID] = Counter()
            for delivery in candidates:
                if len(claimed) >= batch_size:
                    break
                if counts[delivery.tenant_id] >= per_tenant:
                    continue
                snapshot = dict(delivery.route_snapshot)
                policy = _snapshot_policy(snapshot)
                token = self._uuid_source.new_uuid()
                attempt_id = self._uuid_source.new_uuid()
                attempt_number = delivery.attempts_started + 1
                delivery.state = DeliveryState.LEASED.value
                delivery.attempts_started = attempt_number
                delivery.lease_token = token
                delivery.lease_expires_at = now + timedelta(seconds=policy.lease_duration_seconds)
                delivery.updated_at = now
                attempt = AttemptRow(
                    tenant_id=delivery.tenant_id,
                    attempt_id=attempt_id,
                    delivery_id=delivery.delivery_id,
                    attempt_number=attempt_number,
                    lease_token=token,
                    outcome=AttemptOutcome.STARTED.value,
                    started_at=now,
                )
                session.add(attempt)
                event = await session.scalar(
                    select(EventRow).where(
                        EventRow.tenant_id == delivery.tenant_id,
                        EventRow.event_id == delivery.event_id,
                    )
                )
                if event is None:
                    raise MergenConfigurationError("Delivery references a missing event.")
                await session.flush()
                claimed.append(
                    ClaimedDelivery(
                        event=event_from_row(event),
                        delivery=delivery_from_row(delivery),
                        attempt=attempt_from_row(attempt),
                        route_snapshot=snapshot,
                    )
                )
                counts[delivery.tenant_id] += 1
        for claim in claimed:
            self._record(
                RuntimeEventKind.CLAIMED,
                now,
                claim,
                {"destination.kind": claim.delivery.destination_kind},
            )
        return tuple(claimed)

    async def succeed(
        self,
        session: AsyncSession,
        claim: ClaimedDelivery,
        *,
        now: datetime,
    ) -> None:
        async with _owned_transaction(session):
            await self.succeed_in_transaction(session, claim, now=now)
        self._record(
            RuntimeEventKind.SUCCEEDED,
            now,
            claim,
            {"destination.kind": claim.delivery.destination_kind},
        )

    async def succeed_in_transaction(
        self,
        session: AsyncSession,
        claim: ClaimedDelivery,
        *,
        now: datetime,
    ) -> None:
        if not session.in_transaction():
            raise MergenConfigurationError("Transactional success requires an active transaction.")
        delivery, attempt = await _locked_active_rows(session, claim)
        attempt.outcome = AttemptOutcome.SUCCEEDED.value
        attempt.finished_at = now
        delivery.state = DeliveryState.SUCCEEDED.value
        _clear_lease(delivery, now)

    async def fail(
        self,
        session: AsyncSession,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
        *,
        now: datetime,
        retry_after: timedelta | None = None,
    ) -> DeliveryState:
        if not isinstance(error, (RetryableDeliveryError, PermanentDeliveryError)):
            raise MergenConfigurationError("Delivery failures must use a safe classified error.")
        async with _owned_transaction(session):
            outcome = await self.fail_in_transaction(
                session,
                claim,
                error,
                now=now,
                retry_after=retry_after,
            )
        self._record(
            RuntimeEventKind.RETRY_SCHEDULED
            if outcome is DeliveryState.RETRY_WAIT
            else RuntimeEventKind.DEAD,
            now,
            claim,
            {"destination.kind": claim.delivery.destination_kind, "state": outcome.value},
        )
        return outcome

    async def fail_in_transaction(
        self,
        session: AsyncSession,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
        *,
        now: datetime,
        retry_after: timedelta | None = None,
    ) -> DeliveryState:
        if not session.in_transaction():
            raise MergenConfigurationError("Transactional failure requires an active transaction.")
        delivery, attempt = await _locked_active_rows(session, claim)
        policy = _snapshot_policy(dict(delivery.route_snapshot))
        attempt.finished_at = now
        attempt.failure_code = error.code
        attempt.failure_summary = error.summary
        retryable = isinstance(error, RetryableDeliveryError)
        if retryable and policy.permits_retry(
            attempt_number=attempt.attempt_number,
            first_attempt_at=delivery.created_at,
            now=now,
        ):
            attempt.outcome = AttemptOutcome.RETRYABLE.value
            delay = policy.retry_delay(attempt.attempt_number, self._random_source)
            if retry_after is not None:
                if retry_after.total_seconds() < 0:
                    raise MergenConfigurationError("Retry-After cannot be negative.")
                delay = max(delay, retry_after)
            delay = min(delay, timedelta(seconds=policy.maximum_delay_seconds))
            delivery.state = DeliveryState.RETRY_WAIT.value
            delivery.next_attempt_at = now + delay
            outcome = DeliveryState.RETRY_WAIT
        else:
            attempt.outcome = (
                AttemptOutcome.RETRYABLE.value if retryable else AttemptOutcome.TERMINAL.value
            )
            delivery.state = DeliveryState.DEAD.value
            outcome = DeliveryState.DEAD
        _clear_lease(delivery, now)
        return outcome

    async def reconcile_expired(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        batch_size: int = 100,
    ) -> int:
        _require_idle(session)
        _positive("batch_size", batch_size)
        reconciled = 0
        async with session.begin():
            rows = (
                await session.scalars(
                    select(DeliveryRow)
                    .where(
                        DeliveryRow.state == DeliveryState.LEASED.value,
                        DeliveryRow.lease_expires_at <= now,
                    )
                    .order_by(DeliveryRow.lease_expires_at)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for delivery in rows:
                attempt = await session.scalar(
                    select(AttemptRow)
                    .where(
                        AttemptRow.tenant_id == delivery.tenant_id,
                        AttemptRow.delivery_id == delivery.delivery_id,
                        AttemptRow.lease_token == delivery.lease_token,
                        AttemptRow.outcome == AttemptOutcome.STARTED.value,
                    )
                    .with_for_update()
                )
                if attempt is not None:
                    attempt.outcome = AttemptOutcome.ABANDONED.value
                    attempt.finished_at = now
                    attempt.failure_code = "lease.expired"
                    attempt.failure_summary = "Worker lease expired before finalization."
                policy = _snapshot_policy(dict(delivery.route_snapshot))
                delivery.state = (
                    DeliveryState.RETRY_WAIT.value
                    if delivery.attempts_started < policy.max_attempts
                    else DeliveryState.DEAD.value
                )
                delivery.next_attempt_at = now
                _clear_lease(delivery, now)
                reconciled += 1
        if reconciled:
            record_safely(
                self._event_sink,
                RuntimeEvent(
                    RuntimeEventKind.RECONCILED,
                    now,
                    {"reconciled.count": reconciled},
                ),
            )
        return reconciled

    async def replay(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        delivery_id: UUID,
        actor: str,
        reason: str,
        now: datetime,
    ) -> DeliveryRecord:
        """Create new linked work without mutating the terminal original."""
        if not isinstance(actor, str) or not actor or len(actor) > 512:
            raise MergenConfigurationError("Replay actor is invalid.")
        if not isinstance(reason, str) or not reason:
            raise MergenConfigurationError("Replay reason is invalid.")
        async with _owned_transaction(session):
            replay = await self.replay_in_transaction(
                session,
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                actor=actor,
                reason=reason,
                now=now,
            )
        record_safely(
            self._event_sink,
            RuntimeEvent(
                RuntimeEventKind.REPLAYED,
                now,
                {"destination.kind": replay.destination_kind},
                TraceLineage(
                    delivery_id=replay.delivery_id,
                    replay_of=replay.replay_of,
                ),
            ),
        )
        return replay

    async def replay_in_transaction(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        delivery_id: UUID,
        actor: str,
        reason: str,
        now: datetime,
    ) -> DeliveryRecord:
        """Create replay work inside an already active caller-owned transaction."""
        if not session.in_transaction():
            raise MergenConfigurationError("Transactional replay requires an active transaction.")
        if not isinstance(actor, str) or not actor or len(actor) > 512:
            raise MergenConfigurationError("Replay actor is invalid.")
        if not isinstance(reason, str) or not reason:
            raise MergenConfigurationError("Replay reason is invalid.")
        original = await session.scalar(
            select(DeliveryRow)
            .where(
                DeliveryRow.tenant_id == tenant_id,
                DeliveryRow.delivery_id == delivery_id,
            )
            .with_for_update()
        )
        if original is None or original.state not in {
            DeliveryState.SUCCEEDED.value,
            DeliveryState.DEAD.value,
        }:
            raise MergenConfigurationError("Only a terminal delivery can be replayed.")
        replay = DeliveryRow(
            tenant_id=original.tenant_id,
            delivery_id=self._uuid_source.new_uuid(),
            event_id=original.event_id,
            route_key=original.route_key,
            route_version=original.route_version,
            destination_kind=original.destination_kind,
            destination_key=original.destination_key,
            route_snapshot=dict(original.route_snapshot),
            route_snapshot_bytes=bytes(original.route_snapshot_bytes),
            state=DeliveryState.PENDING.value,
            attempts_started=0,
            next_attempt_at=now,
            replay_of=original.delivery_id,
            replay_actor=actor,
            replay_reason=reason,
            created_at=now,
            updated_at=now,
        )
        session.add(replay)
        await session.flush()
        return delivery_from_row(replay)

    def _record(
        self,
        kind: RuntimeEventKind,
        now: datetime,
        claim: ClaimedDelivery,
        attributes: dict[str, str | int | float | bool],
    ) -> None:
        record_safely(
            self._event_sink,
            RuntimeEvent(
                kind,
                now,
                attributes,
                TraceLineage(
                    event_id=claim.event.event_id,
                    delivery_id=claim.delivery.delivery_id,
                    attempt_id=claim.attempt.attempt_id,
                    replay_of=claim.delivery.replay_of,
                    traceparent=claim.event.traceparent,
                ),
            ),
        )


class _owned_transaction:
    def __init__(self, session: AsyncSession) -> None:
        _require_idle(session)
        self._transaction = session.begin()

    async def __aenter__(self) -> None:
        await self._transaction.__aenter__()

    async def __aexit__(self, *args: object) -> None:
        await self._transaction.__aexit__(*args)


async def _locked_active_rows(
    session: AsyncSession,
    claim: ClaimedDelivery,
) -> tuple[DeliveryRow, AttemptRow]:
    delivery = await session.scalar(
        select(DeliveryRow)
        .where(
            DeliveryRow.tenant_id == claim.delivery.tenant_id,
            DeliveryRow.delivery_id == claim.delivery.delivery_id,
        )
        .with_for_update()
    )
    if (
        delivery is None
        or delivery.state != DeliveryState.LEASED.value
        or delivery.lease_token != claim.lease_token
    ):
        raise LeaseLost(delivery_id=claim.delivery.delivery_id)
    attempt = await session.scalar(
        select(AttemptRow)
        .where(
            AttemptRow.tenant_id == claim.attempt.tenant_id,
            AttemptRow.attempt_id == claim.attempt.attempt_id,
            AttemptRow.lease_token == claim.lease_token,
            AttemptRow.outcome == AttemptOutcome.STARTED.value,
        )
        .with_for_update()
    )
    if attempt is None:
        raise LeaseLost(delivery_id=claim.delivery.delivery_id)
    return delivery, attempt


def _snapshot_policy(snapshot: dict[str, Any]) -> RetryPolicy:
    retry = snapshot.get("retry")
    if not isinstance(retry, dict):
        raise MergenConfigurationError("Delivery retry snapshot is invalid.")
    return RetryPolicy.from_dict(retry)


def _clear_lease(delivery: DeliveryRow, now: datetime) -> None:
    delivery.lease_token = None
    delivery.lease_expires_at = None
    delivery.updated_at = now


def _require_idle(session: AsyncSession) -> None:
    if session.in_transaction():
        raise MergenConfigurationError("Lease operation requires an idle control session.")


def _positive(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise MergenConfigurationError(f"Lease {name} must be positive.")


__all__ = ["ClaimedDelivery", "LeaseRepository"]

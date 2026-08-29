"""Short-transaction durable Taskiq handoff repository and fencing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.core.delivery import AttemptOutcome, DeliveryState
from fastapi_mergen.core.identity import UUIDSource
from fastapi_mergen.core.protocols import UUIDGenerator
from fastapi_mergen.core.retry import RetryPolicy, remaining_attempt_seconds
from fastapi_mergen.errors import (
    LeaseLost,
    MergenConfigurationError,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_mergen.executors.protocols import HandoffState
from fastapi_mergen.executors.taskiq.envelope import TaskiqHandoffEnvelope, stable_task_id
from fastapi_mergen.executors.taskiq.models import TaskiqHandoffRow
from fastapi_mergen.postgres.leasing import ClaimedDelivery, LeaseRepository
from fastapi_mergen.sqlalchemy.models import AttemptRow, DeliveryRow, EventRow
from fastapi_mergen.sqlalchemy.repository import attempt_from_row, delivery_from_row, event_from_row


@dataclass(frozen=True, slots=True)
class HandoffRecord:
    tenant_id: UUID
    handoff_id: UUID
    delivery_id: UUID
    attempt_id: UUID
    task_id: str
    state: HandoffState
    execution_count: int
    prepared_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ExecutingHandoff:
    record: HandoffRecord
    claim: ClaimedDelivery
    execution_token: UUID = field(repr=False)
    execution_deadline: datetime


class TaskiqHandoffStore:
    def __init__(
        self,
        *,
        uuid_source: UUIDGenerator | None = None,
        leases: LeaseRepository | None = None,
    ) -> None:
        self._uuid_source = uuid_source or UUIDSource()
        self._leases = leases or LeaseRepository()

    async def prepare(
        self,
        session: AsyncSession,
        *,
        claim: ClaimedDelivery,
        now: datetime,
    ) -> TaskiqHandoffEnvelope:
        _require_idle(session)
        handoff_id = self._uuid_source.new_uuid()
        handoff_token = self._uuid_source.new_uuid()
        task_id = stable_task_id(claim.attempt.attempt_id)
        async with session.begin():
            statement = (
                pg_insert(TaskiqHandoffRow)
                .values(
                    tenant_id=claim.delivery.tenant_id,
                    handoff_id=handoff_id,
                    delivery_id=claim.delivery.delivery_id,
                    attempt_id=claim.attempt.attempt_id,
                    task_id=task_id,
                    handoff_token=handoff_token,
                    state=HandoffState.PREPARED.value,
                    principal=claim.event.principal.to_dict(),
                    route_snapshot=claim.route_snapshot,
                    route_snapshot_bytes=claim.delivery.route_snapshot,
                    event_metadata={
                        "event_id": str(claim.event.event_id),
                        "event_type": claim.event.event_type,
                        "event_version": claim.event.event_version,
                        "occurred_at": claim.event.occurred_at.isoformat(),
                    },
                    execution_count=0,
                    prepared_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=(
                        TaskiqHandoffRow.tenant_id,
                        TaskiqHandoffRow.delivery_id,
                        TaskiqHandoffRow.attempt_id,
                    )
                )
                .returning(TaskiqHandoffRow.handoff_id)
            )
            inserted = await session.scalar(statement)
            row = await session.scalar(
                select(TaskiqHandoffRow).where(
                    TaskiqHandoffRow.tenant_id == claim.delivery.tenant_id,
                    TaskiqHandoffRow.delivery_id == claim.delivery.delivery_id,
                    TaskiqHandoffRow.attempt_id == claim.attempt.attempt_id,
                )
            )
            if row is None or (inserted is None and row.state != HandoffState.PREPARED.value):
                raise MergenConfigurationError("Taskiq handoff preparation conflicted.")
        return _envelope(row)

    async def mark_enqueued(
        self,
        session: AsyncSession,
        *,
        envelope: TaskiqHandoffEnvelope,
        now: datetime,
    ) -> HandoffRecord:
        _require_idle(session)
        async with session.begin():
            row = await self._locked_for_envelope(session, envelope)
            if row.state != HandoffState.PREPARED.value:
                if row.enqueued_at is None:
                    row.enqueued_at = now
                    row.updated_at = now
                return _record(row)
            row.state = HandoffState.ENQUEUED.value
            row.enqueued_at = now
            row.updated_at = now
            await session.flush()
            return _record(row)

    async def enqueue_failed(
        self,
        session: AsyncSession,
        *,
        envelope: TaskiqHandoffEnvelope,
        now: datetime,
    ) -> HandoffRecord:
        _require_idle(session)
        async with session.begin():
            row = await self._locked_for_envelope(session, envelope)
            if row.state != HandoffState.PREPARED.value:
                return _record(row)
            claim = await _claim_for_row(session, row)
            outcome = await self._leases.fail_in_transaction(
                session,
                claim,
                RetryableDeliveryError(
                    code="executor.enqueue_failed",
                    summary="Taskiq broker enqueue did not complete.",
                ),
                now=now,
            )
            _set_failed(row, outcome=outcome, now=now, code="executor.enqueue_failed")
            await session.flush()
            return _record(row)

    async def claim_execution(
        self,
        session: AsyncSession,
        *,
        envelope: TaskiqHandoffEnvelope,
        now: datetime,
        execution_timeout: timedelta,
    ) -> ExecutingHandoff | None:
        _require_idle(session)
        if execution_timeout <= timedelta(0) or execution_timeout > timedelta(hours=1):
            raise MergenConfigurationError("Taskiq execution timeout is invalid.")
        async with session.begin():
            row = await self._locked_for_envelope(session, envelope)
            if row.state in {
                HandoffState.SUCCEEDED.value,
                HandoffState.RETRY_WAIT.value,
                HandoffState.DEAD.value,
            }:
                return None
            if row.state == HandoffState.EXECUTING.value:
                if row.execution_deadline is not None and row.execution_deadline > now:
                    return None
            elif row.state not in {
                HandoffState.PREPARED.value,
                HandoffState.ENQUEUED.value,
            }:
                return None
            try:
                claim = await _claim_for_row(session, row)
            except LeaseLost:
                _set_failed(
                    row,
                    outcome=DeliveryState.DEAD,
                    now=now,
                    code="executor.stale_attempt",
                    summary="Taskiq handoff no longer owns the parent delivery attempt.",
                )
                await session.flush()
                return None
            lease_deadline = claim.delivery.lease_expires_at
            if lease_deadline is None:
                raise LeaseLost(delivery_id=row.delivery_id)
            retry = claim.route_snapshot.get("retry")
            if not isinstance(retry, dict):
                raise MergenConfigurationError("Taskiq retry snapshot is invalid.")
            policy = RetryPolicy.from_dict(retry)
            remaining = remaining_attempt_seconds(
                policy=policy,
                delivery_created_at=claim.delivery.created_at,
                attempt_started_at=claim.attempt.started_at,
                lease_expires_at=lease_deadline,
                now=now,
                configured_limit_seconds=execution_timeout.total_seconds(),
            )
            if remaining <= 0:
                error = RetryableDeliveryError(
                    code="executor.execution_timeout",
                    summary="Taskiq handoff exceeded the parent attempt deadline before admission.",
                )
                outcome = await self._leases.fail_in_transaction(
                    session,
                    claim,
                    error,
                    now=now,
                )
                _set_failed(
                    row,
                    outcome=outcome,
                    now=now,
                    code=error.code,
                    summary=error.summary,
                )
                await session.flush()
                return None
            token = self._uuid_source.new_uuid()
            deadline = now + timedelta(seconds=remaining)
            row.state = HandoffState.EXECUTING.value
            if row.enqueued_at is None:
                row.enqueued_at = now
            row.execution_token = token
            row.execution_deadline = deadline
            row.execution_count += 1
            row.started_at = now
            row.updated_at = now
            await session.flush()
            return ExecutingHandoff(
                record=_record(row),
                claim=claim,
                execution_token=token,
                execution_deadline=deadline,
            )

    async def finalize_success(
        self,
        session: AsyncSession,
        *,
        executing: ExecutingHandoff,
        now: datetime,
    ) -> HandoffRecord:
        _require_idle(session)
        async with session.begin():
            row = await self._locked_execution(session, executing)
            await self._leases.succeed_in_transaction(session, executing.claim, now=now)
            row.state = HandoffState.SUCCEEDED.value
            row.finished_at = now
            row.updated_at = now
            _clear_execution(row)
            await session.flush()
            return _record(row)

    async def finalize_failure(
        self,
        session: AsyncSession,
        *,
        executing: ExecutingHandoff,
        error: RetryableDeliveryError | PermanentDeliveryError,
        now: datetime,
    ) -> HandoffRecord:
        _require_idle(session)
        async with session.begin():
            row = await self._locked_execution(session, executing)
            outcome = await self._leases.fail_in_transaction(
                session,
                executing.claim,
                error,
                now=now,
                retry_after=(
                    error.retry_after if isinstance(error, RetryableDeliveryError) else None
                ),
            )
            _set_failed(row, outcome=outcome, now=now, code=error.code, summary=error.summary)
            await session.flush()
            return _record(row)

    async def recover_expired(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        enqueue_timeout: timedelta = timedelta(minutes=5),
        batch_size: int = 100,
    ) -> int:
        _require_idle(session)
        if not 1 <= batch_size <= 10_000:
            raise MergenConfigurationError("Taskiq recovery batch size is invalid.")
        recovered = 0
        async with session.begin():
            rows = (
                await session.scalars(
                    select(TaskiqHandoffRow)
                    .where(
                        or_(
                            (
                                TaskiqHandoffRow.state.in_(
                                    (HandoffState.PREPARED.value, HandoffState.ENQUEUED.value)
                                )
                                & (TaskiqHandoffRow.updated_at <= now - enqueue_timeout)
                            ),
                            (
                                (TaskiqHandoffRow.state == HandoffState.EXECUTING.value)
                                & (TaskiqHandoffRow.execution_deadline <= now)
                            ),
                        )
                    )
                    .order_by(TaskiqHandoffRow.updated_at)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                try:
                    claim = await _claim_for_row(session, row)
                    outcome = await self._leases.fail_in_transaction(
                        session,
                        claim,
                        RetryableDeliveryError(
                            code="executor.handoff_expired",
                            summary="Taskiq handoff expired before fenced completion.",
                        ),
                        now=now,
                    )
                except LeaseLost:
                    outcome = DeliveryState.DEAD
                _set_failed(row, outcome=outcome, now=now, code="executor.handoff_expired")
                recovered += 1
        return recovered

    async def for_id(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        handoff_id: UUID,
    ) -> HandoffRecord | None:
        row = await session.scalar(
            select(TaskiqHandoffRow).where(
                TaskiqHandoffRow.tenant_id == tenant_id,
                TaskiqHandoffRow.handoff_id == handoff_id,
            )
        )
        return None if row is None else _record(row)

    async def _locked_for_envelope(
        self,
        session: AsyncSession,
        envelope: TaskiqHandoffEnvelope,
    ) -> TaskiqHandoffRow:
        row = await session.scalar(
            select(TaskiqHandoffRow)
            .where(
                TaskiqHandoffRow.tenant_id == envelope.tenant_id,
                TaskiqHandoffRow.handoff_id == envelope.handoff_id,
                TaskiqHandoffRow.delivery_id == envelope.delivery_id,
                TaskiqHandoffRow.attempt_id == envelope.attempt_id,
                TaskiqHandoffRow.task_id == envelope.task_id,
                TaskiqHandoffRow.handoff_token == envelope.handoff_token,
            )
            .with_for_update()
        )
        if row is None:
            raise MergenConfigurationError("Taskiq handoff envelope was rejected.")
        return row

    async def _locked_execution(
        self,
        session: AsyncSession,
        executing: ExecutingHandoff,
    ) -> TaskiqHandoffRow:
        row = await session.scalar(
            select(TaskiqHandoffRow)
            .where(
                TaskiqHandoffRow.tenant_id == executing.record.tenant_id,
                TaskiqHandoffRow.handoff_id == executing.record.handoff_id,
            )
            .with_for_update()
        )
        if (
            row is None
            or row.state != HandoffState.EXECUTING.value
            or row.execution_token != executing.execution_token
        ):
            raise LeaseLost(delivery_id=executing.record.delivery_id)
        return row


async def _claim_for_row(session: AsyncSession, row: TaskiqHandoffRow) -> ClaimedDelivery:
    delivery = await session.scalar(
        select(DeliveryRow)
        .where(
            DeliveryRow.tenant_id == row.tenant_id,
            DeliveryRow.delivery_id == row.delivery_id,
        )
        .with_for_update()
    )
    attempt = await session.scalar(
        select(AttemptRow)
        .where(
            AttemptRow.tenant_id == row.tenant_id,
            AttemptRow.attempt_id == row.attempt_id,
        )
        .with_for_update()
    )
    if (
        delivery is None
        or attempt is None
        or delivery.state != DeliveryState.LEASED.value
        or delivery.lease_token is None
        or attempt.delivery_id != row.delivery_id
        or attempt.lease_token != delivery.lease_token
        or attempt.outcome != AttemptOutcome.STARTED.value
    ):
        raise LeaseLost(delivery_id=row.delivery_id)
    event = await session.scalar(
        select(EventRow).where(
            EventRow.tenant_id == row.tenant_id,
            EventRow.event_id == delivery.event_id,
        )
    )
    if event is None:
        raise MergenConfigurationError("Taskiq handoff event no longer exists.")
    return ClaimedDelivery(
        event=event_from_row(event),
        delivery=delivery_from_row(delivery),
        attempt=attempt_from_row(attempt),
        route_snapshot=dict(row.route_snapshot),
    )


def _envelope(row: TaskiqHandoffRow) -> TaskiqHandoffEnvelope:
    return TaskiqHandoffEnvelope(
        tenant_id=row.tenant_id,
        handoff_id=row.handoff_id,
        delivery_id=row.delivery_id,
        attempt_id=row.attempt_id,
        task_id=row.task_id,
        handoff_token=row.handoff_token,
    )


def _record(row: TaskiqHandoffRow) -> HandoffRecord:
    return HandoffRecord(
        tenant_id=row.tenant_id,
        handoff_id=row.handoff_id,
        delivery_id=row.delivery_id,
        attempt_id=row.attempt_id,
        task_id=row.task_id,
        state=HandoffState(row.state),
        execution_count=row.execution_count,
        prepared_at=row.prepared_at,
        updated_at=row.updated_at,
    )


def _set_failed(
    row: TaskiqHandoffRow,
    *,
    outcome: DeliveryState,
    now: datetime,
    code: str,
    summary: str = "Taskiq handoff failed before completion.",
) -> None:
    row.state = (
        HandoffState.RETRY_WAIT.value
        if outcome is DeliveryState.RETRY_WAIT
        else HandoffState.DEAD.value
    )
    row.finished_at = now
    row.updated_at = now
    row.failure_code = code
    row.failure_summary = summary
    _clear_execution(row)


def _clear_execution(row: TaskiqHandoffRow) -> None:
    row.execution_token = None
    row.execution_deadline = None


def _require_idle(session: AsyncSession) -> None:
    if session.in_transaction():
        raise MergenConfigurationError("Taskiq handoff operation requires an idle session.")


__all__ = ["ExecutingHandoff", "HandoffRecord", "TaskiqHandoffStore"]

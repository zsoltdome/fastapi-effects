"""Duplicate-safe Taskiq worker bridge with principal/session cleanup delegated to handlers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_effects.core.protocols import Clock
from fastapi_effects.core.runtime import SystemClock
from fastapi_effects.errors import (
    AuthorizationDenied,
    AuthorizationExpired,
    FastAPIEffectsConfigurationError,
    LeaseLost,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_effects.executors.protocols import HandoffExecutor
from fastapi_effects.executors.taskiq.envelope import TaskiqHandoffEnvelope
from fastapi_effects.executors.taskiq.store import HandoffRecord, TaskiqHandoffStore
from fastapi_effects.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_effects.observability.protocols import EventSink, NoOpEventSink, record_safely
from fastapi_effects.postgres.errors import is_transient_database_error


@dataclass(frozen=True, slots=True)
class WorkerResult:
    handoff_id: str
    task_id: str
    status: str
    executed: bool
    execution_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "handoff_id": self.handoff_id,
            "task_id": self.task_id,
            "status": self.status,
            "executed": self.executed,
            "execution_count": self.execution_count,
        }


@dataclass(slots=True)
class TaskiqWorkerBridge:
    sessions: async_sessionmaker[AsyncSession]
    executor: HandoffExecutor
    store: TaskiqHandoffStore = field(default_factory=TaskiqHandoffStore)
    clock: Clock = field(default_factory=SystemClock)
    execution_timeout: timedelta = timedelta(minutes=5)
    control_plane_timeout: timedelta = timedelta(seconds=10)
    event_sink: EventSink = field(default_factory=NoOpEventSink)

    def __post_init__(self) -> None:
        if (
            self.execution_timeout <= timedelta(0)
            or self.execution_timeout > timedelta(hours=1)
            or self.control_plane_timeout <= timedelta(0)
            or self.control_plane_timeout > timedelta(minutes=5)
        ):
            raise FastAPIEffectsConfigurationError("Taskiq worker operation budgets are invalid.")

    async def execute(self, value: dict[str, object]) -> WorkerResult:
        envelope = TaskiqHandoffEnvelope.from_dict(value)
        async with asyncio.timeout(self.control_plane_timeout.total_seconds()):
            async with self.sessions() as session:
                executing = await self.store.claim_execution(
                    session,
                    envelope=envelope,
                    now=self.clock.now(),
                    execution_timeout=self.execution_timeout,
                )
        if executing is None:
            async with asyncio.timeout(self.control_plane_timeout.total_seconds()):
                async with self.sessions() as session:
                    record = await self.store.for_id(
                        session,
                        tenant_id=envelope.tenant_id,
                        handoff_id=envelope.handoff_id,
                    )
            if record is None:
                raise FastAPIEffectsConfigurationError("Taskiq duplicate references no handoff.")
            self._record(envelope, record, executed=False)
            return _result(record, executed=False)
        failure: RetryableDeliveryError | PermanentDeliveryError | None = None
        try:
            remaining = (executing.execution_deadline - self.clock.now()).total_seconds()
            if remaining <= 0:
                raise TimeoutError
            async with asyncio.timeout(remaining):
                await self.executor.execute(executing.claim)
        except asyncio.CancelledError:
            raise
        except (AuthorizationDenied, AuthorizationExpired, PermanentDeliveryError) as exc:
            failure = (
                exc
                if isinstance(exc, PermanentDeliveryError)
                else PermanentDeliveryError(
                    code="executor.authorization_denied",
                    summary="Taskiq handler authority was denied.",
                )
            )
        except RetryableDeliveryError as exc:
            failure = exc
        except TimeoutError:
            failure = RetryableDeliveryError(
                code="executor.execution_timeout",
                summary="Taskiq handler exceeded its aggregate attempt deadline.",
            )
        except Exception as exc:
            if is_transient_database_error(exc):
                # Commit status may be unknown. Leave the executing handoff for
                # fenced recovery instead of manufacturing a business retry.
                raise
            failure = RetryableDeliveryError(
                code="executor.execution_failed",
                summary="Taskiq handler failed without safe classification.",
            )
        try:
            async with asyncio.timeout(self.control_plane_timeout.total_seconds()):
                async with self.sessions() as session:
                    if failure is None:
                        record = await self.store.finalize_success(
                            session,
                            executing=executing,
                            now=self.clock.now(),
                        )
                    else:
                        record = await self.store.finalize_failure(
                            session,
                            executing=executing,
                            error=failure,
                            now=self.clock.now(),
                        )
        except LeaseLost as exc:
            async with asyncio.timeout(self.control_plane_timeout.total_seconds()):
                async with self.sessions() as session:
                    current = await self.store.for_id(
                        session,
                        tenant_id=envelope.tenant_id,
                        handoff_id=envelope.handoff_id,
                    )
            if current is None:
                raise FastAPIEffectsConfigurationError(
                    "Taskiq stale finalization lost its handoff."
                ) from exc
            record = current
        self._record(envelope, record, executed=True)
        return _result(record, executed=True)

    def _record(
        self,
        envelope: TaskiqHandoffEnvelope,
        record: HandoffRecord,
        *,
        executed: bool,
    ) -> None:
        record_safely(
            self.event_sink,
            RuntimeEvent(
                RuntimeEventKind.TASKIQ_EXECUTED,
                self.clock.now(),
                {
                    "capability": "taskiq",
                    "state": record.state.value,
                    "executed": executed,
                },
                TraceLineage(
                    delivery_id=envelope.delivery_id,
                    attempt_id=envelope.attempt_id,
                    handoff_id=envelope.handoff_id,
                ),
            ),
        )


def _result(record: HandoffRecord, *, executed: bool) -> WorkerResult:
    return WorkerResult(
        handoff_id=str(record.handoff_id),
        task_id=record.task_id,
        status=record.state.value,
        executed=executed,
        execution_count=record.execution_count,
    )


__all__ = ["TaskiqWorkerBridge", "WorkerResult"]

"""Duplicate-safe Taskiq worker bridge with principal/session cleanup delegated to handlers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_mergen.core.protocols import Clock
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.errors import (
    AuthorizationDenied,
    AuthorizationExpired,
    MergenConfigurationError,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_mergen.executors.protocols import HandoffExecutor
from fastapi_mergen.executors.taskiq.envelope import TaskiqHandoffEnvelope
from fastapi_mergen.executors.taskiq.store import HandoffRecord, TaskiqHandoffStore
from fastapi_mergen.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_mergen.observability.protocols import EventSink, NoOpEventSink, record_safely


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
    event_sink: EventSink = field(default_factory=NoOpEventSink)

    async def execute(self, value: dict[str, object]) -> WorkerResult:
        envelope = TaskiqHandoffEnvelope.from_dict(value)
        async with self.sessions() as session:
            executing = await self.store.claim_execution(
                session,
                envelope=envelope,
                now=self.clock.now(),
                execution_timeout=self.execution_timeout,
            )
        if executing is None:
            async with self.sessions() as session:
                record = await self.store.for_id(
                    session,
                    tenant_id=envelope.tenant_id,
                    handoff_id=envelope.handoff_id,
                )
            if record is None:
                raise MergenConfigurationError("Taskiq duplicate references no handoff.")
            self._record(envelope, record, executed=False)
            return _result(record, executed=False)
        try:
            await self.executor.execute(executing.claim)
        except asyncio.CancelledError:
            raise
        except (AuthorizationDenied, AuthorizationExpired, PermanentDeliveryError) as exc:
            error = (
                exc
                if isinstance(exc, PermanentDeliveryError)
                else PermanentDeliveryError(
                    code="executor.authorization_denied",
                    summary="Taskiq handler authority was denied.",
                )
            )
            async with self.sessions() as session:
                record = await self.store.finalize_failure(
                    session,
                    executing=executing,
                    error=error,
                    now=self.clock.now(),
                )
        except RetryableDeliveryError as exc:
            async with self.sessions() as session:
                record = await self.store.finalize_failure(
                    session,
                    executing=executing,
                    error=exc,
                    now=self.clock.now(),
                )
        except Exception:
            async with self.sessions() as session:
                record = await self.store.finalize_failure(
                    session,
                    executing=executing,
                    error=RetryableDeliveryError(
                        code="executor.execution_failed",
                        summary="Taskiq handler failed without safe classification.",
                    ),
                    now=self.clock.now(),
                )
        else:
            async with self.sessions() as session:
                record = await self.store.finalize_success(
                    session,
                    executing=executing,
                    now=self.clock.now(),
                )
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

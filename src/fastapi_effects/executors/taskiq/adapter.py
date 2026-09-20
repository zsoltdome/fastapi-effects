"""Taskiq enqueue bridge; broker acknowledgement remains nonterminal."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_effects._optional import require_modules
from fastapi_effects.core.protocols import Clock
from fastapi_effects.core.retry import RetryPolicy, remaining_attempt_seconds
from fastapi_effects.core.runtime import SystemClock
from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.executors.taskiq.envelope import TaskiqHandoffEnvelope
from fastapi_effects.executors.taskiq.store import TaskiqHandoffStore
from fastapi_effects.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_effects.observability.protocols import EventSink, NoOpEventSink, record_safely
from fastapi_effects.postgres.leasing import ClaimedDelivery
from fastapi_effects.postgres.relay import SinkDisposition

BRIDGE_TASK_NAME = "fastapi_effects.taskiq.execute_handoff"


class TaskiqKicker(Protocol):
    def with_labels(self, **labels: str) -> TaskiqKicker: ...

    def with_task_id(self, task_id: str) -> TaskiqKicker: ...

    async def kiq(self, *args: object, **kwargs: object) -> Any: ...


class TaskiqDecoratedTask(Protocol):
    def kicker(self) -> TaskiqKicker: ...


@dataclass(slots=True)
class TaskiqDeliverySink:
    sessions: async_sessionmaker[AsyncSession]
    task: TaskiqDecoratedTask
    store: TaskiqHandoffStore = field(default_factory=TaskiqHandoffStore)
    clock: Clock = field(default_factory=SystemClock)
    event_sink: EventSink = field(default_factory=NoOpEventSink)

    async def execute(self, claim: ClaimedDelivery) -> SinkDisposition:
        retry = claim.route_snapshot.get("retry")
        lease_expires_at = claim.delivery.lease_expires_at
        if not isinstance(retry, dict) or lease_expires_at is None:
            raise FastAPIEffectsConfigurationError("Taskiq enqueue attempt deadline is invalid.")
        timeout_seconds = remaining_attempt_seconds(
            policy=RetryPolicy.from_dict(retry),
            delivery_created_at=claim.delivery.created_at,
            attempt_started_at=claim.attempt.started_at,
            lease_expires_at=lease_expires_at,
            now=self.clock.now(),
        )
        if timeout_seconds <= 0:
            return SinkDisposition.DEFERRED
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._execute(claim)
        except TimeoutError:
            # Broker acceptance is ambiguous. Any prepared handoff and the stable
            # task ID let worker execution or bounded recovery win safely.
            return SinkDisposition.DEFERRED

    async def _execute(self, claim: ClaimedDelivery) -> SinkDisposition:
        now = self.clock.now()
        async with self.sessions() as session:
            envelope = await self.store.prepare(session, claim=claim, now=now)
        self._record(RuntimeEventKind.TASKIQ_PREPARED, envelope, now, "prepared")
        kicker = (
            self.task.kicker()
            .with_labels(fastapi_effects_retry_owner="true", retry_on_error="false")
            .with_task_id(envelope.task_id)
        )
        try:
            broker_task = await kicker.kiq(envelope.to_dict())
        except asyncio.CancelledError:
            # Acceptance is ambiguous. Prepared state and stable Taskiq ID allow
            # either a delivered worker message or bounded recovery to win safely.
            raise
        except Exception:
            async with self.sessions() as session:
                await self.store.enqueue_failed(session, envelope=envelope, now=self.clock.now())
            return SinkDisposition.DEFERRED
        returned_id = getattr(broker_task, "task_id", envelope.task_id)
        if returned_id != envelope.task_id:
            async with self.sessions() as session:
                await self.store.enqueue_failed(session, envelope=envelope, now=self.clock.now())
            return SinkDisposition.DEFERRED
        async with self.sessions() as session:
            await self.store.mark_enqueued(session, envelope=envelope, now=self.clock.now())
        self._record(RuntimeEventKind.TASKIQ_ENQUEUED, envelope, self.clock.now(), "enqueued")
        return SinkDisposition.DEFERRED

    def _record(
        self,
        kind: RuntimeEventKind,
        envelope: TaskiqHandoffEnvelope,
        now: datetime,
        state: str,
    ) -> None:
        record_safely(
            self.event_sink,
            RuntimeEvent(
                kind,
                now,
                {"capability": "taskiq", "state": state},
                TraceLineage(
                    delivery_id=envelope.delivery_id,
                    attempt_id=envelope.attempt_id,
                    handoff_id=envelope.handoff_id,
                ),
            ),
        )


def register_taskiq_bridge(broker: Any, worker: Any) -> TaskiqDecoratedTask:
    """Register exactly one bridge task using Taskiq's supported decorator API."""
    require_modules(
        feature="Taskiq executor adapter",
        extra="taskiq",
        modules=("taskiq",),
    )

    async def execute_handoff(envelope: dict[str, object]) -> dict[str, object]:
        result = await worker.execute(envelope)
        return cast(dict[str, object], result.to_dict())

    task = broker.task(task_name=BRIDGE_TASK_NAME)(execute_handoff)
    return cast(TaskiqDecoratedTask, task)


__all__ = [
    "BRIDGE_TASK_NAME",
    "TaskiqDecoratedTask",
    "TaskiqDeliverySink",
    "TaskiqKicker",
    "register_taskiq_bridge",
]

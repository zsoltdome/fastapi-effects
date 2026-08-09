"""Real PostgreSQL plus Taskiq broker adapter for the executor profile."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from taskiq import InMemoryBroker

from fastapi_mergen.conformance.contract import Capability, Invariant
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.protocols import ExecutorHandoffView
from fastapi_mergen.core.delivery import (
    AttemptOutcome,
    AttemptRecord,
    DeliveryRecord,
    DeliveryState,
)
from fastapi_mergen.core.event import EventRecord
from fastapi_mergen.core.policy import AuthorizationMode
from fastapi_mergen.core.principal import Principal, PrincipalEnvelope
from fastapi_mergen.core.retry import RetryPolicy
from fastapi_mergen.core.routing import RouteSpecification
from fastapi_mergen.executors.taskiq.adapter import (
    TaskiqDeliverySink,
    register_taskiq_bridge,
)
from fastapi_mergen.executors.taskiq.envelope import TaskiqHandoffEnvelope
from fastapi_mergen.executors.taskiq.models import TaskiqHandoffRow
from fastapi_mergen.executors.taskiq.store import TaskiqHandoffStore
from fastapi_mergen.executors.taskiq.worker import TaskiqWorkerBridge
from fastapi_mergen.postgres.leasing import ClaimedDelivery
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.sqlalchemy.canonical import canonical_sha256, versioned_canonical_bytes
from fastapi_mergen.sqlalchemy.models import AttemptRow, DeliveryRow, EventRow
from fastapi_mergen.testing.postgres_driver import PostgresBoundaryDriver


class _RecordingExecutor:
    def __init__(self) -> None:
        self.execution_count = 0

    async def execute(self, claim: ClaimedDelivery) -> None:
        Principal.from_envelope(claim.event.principal)
        self.execution_count += 1


class _GatedWorker:
    def __init__(self, worker: TaskiqWorkerBridge) -> None:
        self.worker = worker
        self.gate = asyncio.Event()

    async def execute(self, envelope: dict[str, object]) -> object:
        await self.gate.wait()
        return await self.worker.execute(envelope)


class PostgresTaskiqBoundaryDriver(PostgresBoundaryDriver):
    def __init__(
        self,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> None:
        super().__init__(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        self._relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
        self._broker = InMemoryBroker()
        self._store = TaskiqHandoffStore()
        self._executor = _RecordingExecutor()
        worker = TaskiqWorkerBridge(
            sessions=self._relay_sessions,
            executor=self._executor,
            store=self._store,
            execution_timeout=timedelta(seconds=30),
        )
        self._gated = _GatedWorker(worker)
        self._bridge_task = register_taskiq_bridge(self._broker, self._gated)
        self._sink = TaskiqDeliverySink(
            sessions=self._relay_sessions,
            task=self._bridge_task,
            store=self._store,
        )
        self._envelopes: dict[UUID, TaskiqHandoffEnvelope] = {}

    @classmethod
    async def create(
        cls,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> PostgresTaskiqBoundaryDriver:
        driver = cls(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        await driver._prepare_business_table()
        await driver._broker.startup()
        return driver

    @property
    def manifest(self) -> CapabilityManifest:
        core = super().manifest
        return CapabilityManifest(
            adapter_name="fastapi-mergen-postgresql-taskiq",
            adapter_version="0.9.0a1",
            implementation="fastapi_mergen.testing.taskiq_driver.PostgresTaskiqBoundaryDriver",
            capabilities=core.capabilities | {Capability.EXTERNAL_EXECUTOR},
            invariants=core.invariants | {Invariant.EXECUTOR_HANDOFF},
            metadata={"broker": "taskiq-inmemory", "driver": "asyncpg", "store": "postgresql"},
        )

    async def reset(self) -> None:
        await self._broker.wait_all()
        await super().reset()
        self._gated.gate = asyncio.Event()
        self._envelopes.clear()
        self._executor.execution_count = 0

    async def close(self) -> None:
        self._gated.gate.set()
        await self._broker.wait_all()
        await self._broker.shutdown()
        await super().close()

    async def enqueue_handoff(
        self,
        *,
        principal: Principal,
        delivery_id: UUID,
        attempt_id: UUID,
    ) -> ExecutorHandoffView:
        claim = await self._seed_claim(
            principal=principal,
            delivery_id=delivery_id,
            attempt_id=attempt_id,
        )
        await self._sink.execute(claim)
        async with self._relay_sessions() as session:
            row = await session.scalar(
                select(TaskiqHandoffRow).where(TaskiqHandoffRow.attempt_id == attempt_id)
            )
        if row is None:
            raise AssertionError("Taskiq adapter did not persist a handoff.")
        self._envelopes[row.handoff_id] = _envelope(row)
        return _view(row)

    async def execute_handoff(
        self,
        *,
        handoff_id: UUID,
        worker_id: str,
    ) -> ExecutorHandoffView:
        del worker_id
        envelope = self._envelopes[handoff_id]
        if not self._gated.gate.is_set():
            self._gated.gate.set()
        else:
            await self._bridge_task.kicker().with_task_id(envelope.task_id).kiq(envelope.to_dict())
        await self._broker.wait_all()
        async with self._relay_sessions() as session:
            row = await session.scalar(
                select(TaskiqHandoffRow).where(TaskiqHandoffRow.handoff_id == handoff_id)
            )
        if row is None:
            raise AssertionError("Taskiq handoff disappeared during execution.")
        return _view(row)

    async def _seed_claim(
        self,
        *,
        principal: Principal,
        delivery_id: UUID,
        attempt_id: UUID,
    ) -> ClaimedDelivery:
        now = datetime.now(UTC)
        event_id = uuid4()
        lease_token = uuid4()
        payload: dict[str, object] = {}
        canonical = versioned_canonical_bytes(payload)
        route = RouteSpecification(
            event_type="conformance.executor",
            route_key="conformance.executor",
            version=1,
            destination_kind="handler",
            destination_key="conformance.executor",
            required_scopes=tuple(sorted(principal.scopes)),
            authorization=AuthorizationMode.SNAPSHOT,
            service_policy=None,
            service_capabilities=None,
            maximum_snapshot_age_seconds=3600,
            retry_policy=RetryPolicy(
                name="conformance.executor",
                handler_timeout_seconds=30,
                lease_duration_seconds=60,
            ),
        )
        event = EventRecord(
            event_id=event_id,
            tenant_id=principal.tenant_id,
            event_type="conformance.executor",
            event_version=1,
            canonical_version=1,
            payload_canonical=canonical,
            payload_sha256=canonical_sha256(payload),
            principal=principal.to_envelope(),
            occurred_at=now,
            created_at=now,
        )
        delivery = DeliveryRecord(
            delivery_id=delivery_id,
            tenant_id=principal.tenant_id,
            event_id=event_id,
            route_key=route.route_key,
            route_version=1,
            destination_kind="handler",
            destination_key=route.destination_key,
            route_snapshot=route.snapshot_bytes(),
            state=DeliveryState.LEASED,
            attempts_started=1,
            created_at=now,
            updated_at=now,
            next_attempt_at=now,
            lease_token=lease_token,
            lease_expires_at=now + timedelta(seconds=60),
        )
        attempt = AttemptRecord(
            attempt_id=attempt_id,
            tenant_id=principal.tenant_id,
            delivery_id=delivery_id,
            attempt_number=1,
            lease_token=lease_token,
            outcome=AttemptOutcome.STARTED,
            started_at=now,
        )
        async with self._migration_engine.begin() as connection:
            await connection.execute(
                insert(EventRow).values(
                    tenant_id=principal.tenant_id,
                    event_id=event_id,
                    event_type=event.event_type,
                    event_version=1,
                    canonical_version=1,
                    payload=payload,
                    payload_canonical=canonical,
                    payload_sha256=event.payload_sha256,
                    principal=principal.to_envelope().to_dict(),
                    occurred_at=now,
                    created_at=now,
                )
            )
            await connection.execute(
                insert(DeliveryRow).values(
                    tenant_id=principal.tenant_id,
                    delivery_id=delivery_id,
                    event_id=event_id,
                    route_key=route.route_key,
                    route_version=1,
                    destination_kind="handler",
                    destination_key=route.destination_key,
                    route_snapshot=route.to_snapshot(),
                    route_snapshot_bytes=route.snapshot_bytes(),
                    state="leased",
                    attempts_started=1,
                    next_attempt_at=now,
                    lease_token=lease_token,
                    lease_expires_at=now + timedelta(seconds=60),
                    created_at=now,
                    updated_at=now,
                )
            )
            await connection.execute(
                insert(AttemptRow).values(
                    tenant_id=principal.tenant_id,
                    attempt_id=attempt_id,
                    delivery_id=delivery_id,
                    attempt_number=1,
                    lease_token=lease_token,
                    outcome="started",
                    started_at=now,
                )
            )
        return ClaimedDelivery(
            event=event,
            delivery=delivery,
            attempt=attempt,
            route_snapshot=route.to_snapshot(),
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


def _view(row: TaskiqHandoffRow) -> ExecutorHandoffView:
    principal = PrincipalEnvelope.from_dict(row.principal)
    return ExecutorHandoffView(
        handoff_id=row.handoff_id,
        delivery_id=row.delivery_id,
        attempt_id=row.attempt_id,
        task_id=row.task_id,
        status=row.state,
        terminal=row.state in {"succeeded", "dead"},
        execution_count=row.execution_count,
        tenant_id=row.tenant_id,
        subject_id=principal.subject_id,
        scopes=frozenset(principal.scopes),
    )


__all__ = ["PostgresTaskiqBoundaryDriver"]

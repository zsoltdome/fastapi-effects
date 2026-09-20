"""Real PostgreSQL, Redis Streams, and process-isolated Taskiq conformance adapter."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from taskiq_redis import RedisStreamBroker

from fastapi_effects import __version__
from fastapi_effects.conformance.contract import Capability, Invariant
from fastapi_effects.conformance.manifest import CapabilityManifest
from fastapi_effects.conformance.protocols import ExecutorHandoffView
from fastapi_effects.core.delivery import (
    AttemptOutcome,
    AttemptRecord,
    DeliveryRecord,
    DeliveryState,
)
from fastapi_effects.core.event import EventRecord
from fastapi_effects.core.policy import AuthorizationMode
from fastapi_effects.core.principal import Principal, PrincipalEnvelope
from fastapi_effects.core.retry import RetryPolicy
from fastapi_effects.core.routing import RouteSpecification
from fastapi_effects.executors.taskiq.adapter import TaskiqDeliverySink, register_taskiq_bridge
from fastapi_effects.executors.taskiq.envelope import TaskiqHandoffEnvelope
from fastapi_effects.executors.taskiq.models import TaskiqHandoffRow
from fastapi_effects.executors.taskiq.store import TaskiqHandoffStore
from fastapi_effects.postgres.leasing import ClaimedDelivery, LeaseRepository
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.sqlalchemy.canonical import canonical_sha256, versioned_canonical_bytes
from fastapi_effects.sqlalchemy.models import SCHEMA, AttemptRow, DeliveryRow, EventRow
from fastapi_effects.testing.evidence import postgres_evidence_metadata
from fastapi_effects.testing.postgres_driver import PostgresBoundaryDriver


class _ParentProcessGuard:
    async def execute(self, envelope: dict[str, object]) -> object:
        del envelope
        raise AssertionError("Taskiq conformance work executed in the producer process.")


class PostgresTaskiqBoundaryDriver(PostgresBoundaryDriver):
    """Certify a durable handoff across a Redis broker and Taskiq worker process."""

    def __init__(
        self,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
        redis_url: str | None = None,
    ) -> None:
        super().__init__(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        configured_url = redis_url or os.getenv("FASTAPI_EFFECTS_TEST_REDIS_URL")
        if not configured_url:
            raise RuntimeError(
                "Taskiq conformance requires FASTAPI_EFFECTS_TEST_REDIS_URL "
                "for a Redis Streams broker."
            )
        self._redis_url = configured_url
        self._relay_dsn = relay_engine.url.render_as_string(hide_password=False)
        self._queue_name = f"fastapi_effects_conformance-{uuid4().hex}"
        self._relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
        self._broker = RedisStreamBroker(
            url=self._redis_url,
            queue_name=self._queue_name,
            consumer_group_name=f"{self._queue_name}-workers",
            xread_block=100,
            idle_timeout=30_000,
        )
        self._store = TaskiqHandoffStore()
        self._bridge_task = register_taskiq_bridge(self._broker, _ParentProcessGuard())
        self._sink = TaskiqDeliverySink(
            sessions=self._relay_sessions,
            task=self._bridge_task,
            store=self._store,
        )
        self._envelopes: dict[UUID, TaskiqHandoffEnvelope] = {}
        self._worker_process: asyncio.subprocess.Process | None = None
        self._worker_process_started = 0

    @classmethod
    async def create(
        cls,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
        redis_url: str | None = None,
    ) -> PostgresTaskiqBoundaryDriver:
        driver = cls(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
            redis_url=redis_url,
        )
        await driver._prepare_business_table()
        driver._manifest_metadata = await postgres_evidence_metadata(migration_engine)
        await driver._broker.startup()
        return driver

    @property
    def manifest(self) -> CapabilityManifest:
        core = super().manifest
        metadata = dict(core.metadata)
        metadata.update(
            {
                "executor.broker": "taskiq-redis-streams",
                "executor.serialization": "taskiq-broker-message",
                "executor.worker_boundary": "subprocess",
            }
        )
        return CapabilityManifest(
            adapter_name="fastapi_effects_postgresql-taskiq-redis",
            adapter_version=__version__,
            implementation="fastapi_effects.testing.taskiq_driver.PostgresTaskiqBoundaryDriver",
            capabilities=core.capabilities | {Capability.EXTERNAL_EXECUTOR},
            invariants=core.invariants | {Invariant.EXECUTOR_HANDOFF},
            metadata=metadata,
        )

    async def reset(self) -> None:
        await self._stop_worker()
        await super().reset()
        async with self._migration_engine.begin() as connection:
            await connection.execute(text(f"DELETE FROM {SCHEMA}.taskiq_handoffs"))
        self._envelopes.clear()
        self._worker_process_started = 0

    async def close(self) -> None:
        await self._stop_worker()
        await self._broker.shutdown()
        await super().close()

    async def public_evidence(self) -> dict[str, int]:
        evidence = await super().public_evidence()
        evidence["taskiq_worker_processes"] = self._worker_process_started
        return evidence

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
        if self._worker_process is None:
            await self._start_worker()
        else:
            await self._bridge_task.kicker().with_task_id(envelope.task_id).kiq(envelope.to_dict())
            await asyncio.sleep(0.2)
        row = await self._wait_for_terminal_handoff(handoff_id)
        return _view(row)

    async def execute_reclaimed_handoff_pair(
        self,
        *,
        principal: Principal,
        delivery_id: UUID,
        stale_attempt_id: UUID,
    ) -> tuple[ExecutorHandoffView, ExecutorHandoffView]:
        """Delay attempt A, reclaim its parent into B, then run both in a CLI worker."""
        stale = await self.enqueue_handoff(
            principal=principal,
            delivery_id=delivery_id,
            attempt_id=stale_attempt_id,
        )
        async with self._migration_engine.begin() as connection:
            await connection.execute(
                update(DeliveryRow)
                .where(DeliveryRow.delivery_id == delivery_id)
                .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
            )
        reclaimed_at = datetime.now(UTC)
        leases = LeaseRepository()
        async with self._relay_sessions() as session:
            reconciled = await leases.reconcile_expired(session, now=reclaimed_at)
        if reconciled != 1:
            raise AssertionError("Taskiq stale-handoff rehearsal did not reclaim attempt A.")
        async with self._relay_sessions() as session:
            claims = await leases.claim(session, now=reclaimed_at)
        if len(claims) != 1:
            raise AssertionError("Taskiq stale-handoff rehearsal did not create attempt B.")
        current_claim = claims[0]
        await self._sink.execute(current_claim)
        async with self._relay_sessions() as session:
            current_row = await session.scalar(
                select(TaskiqHandoffRow).where(
                    TaskiqHandoffRow.attempt_id == current_claim.attempt.attempt_id
                )
            )
        if current_row is None:
            raise AssertionError("Taskiq stale-handoff rehearsal did not persist attempt B.")
        current_envelope = _envelope(current_row)
        self._envelopes[current_row.handoff_id] = current_envelope
        await (
            self._bridge_task.kicker()
            .with_task_id(current_envelope.task_id)
            .kiq(current_envelope.to_dict())
        )

        current = await self.execute_handoff(
            handoff_id=current_row.handoff_id,
            worker_id="worker:reclaimed",
        )
        stale_row = await self._wait_for_terminal_handoff(stale.handoff_id)
        return _view(stale_row), current

    async def _start_worker(self) -> None:
        environment = os.environ.copy()
        environment.update(
            {
                "FASTAPI_EFFECTS_TASKIQ_REDIS_URL": self._redis_url,
                "FASTAPI_EFFECTS_TASKIQ_RELAY_DSN": self._relay_dsn,
                "FASTAPI_EFFECTS_TASKIQ_QUEUE_NAME": self._queue_name,
                "FASTAPI_EFFECTS_TASKIQ_PARENT_PID": str(os.getpid()),
            }
        )
        self._worker_process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "--workers",
            "1",
            "--max-async-tasks",
            "1",
            "fastapi_effects.testing.taskiq_worker_fixture:broker",
            env=environment,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._worker_process_started += 1

    async def _stop_worker(self) -> None:
        process = self._worker_process
        self._worker_process = None
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _wait_for_terminal_handoff(self, handoff_id: UUID) -> TaskiqHandoffRow:
        for _ in range(100):
            process = self._worker_process
            if process is not None and process.returncode is not None:
                raise AssertionError(
                    f"Taskiq worker exited before completing the handoff ({process.returncode})."
                )
            async with self._relay_sessions() as session:
                row = await session.scalar(
                    select(TaskiqHandoffRow).where(TaskiqHandoffRow.handoff_id == handoff_id)
                )
            if row is not None and row.state in {"succeeded", "dead"}:
                return row
            await asyncio.sleep(0.05)
        raise AssertionError("Taskiq worker did not complete the handoff within five seconds.")

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

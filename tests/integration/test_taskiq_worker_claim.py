from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from taskiq import InMemoryBroker

from fastapi_mergen import (
    AuthorizationMode,
    EffectContext,
    Event,
    Mergen,
    MergenUnitOfWork,
    Principal,
    RetryPolicy,
)
from fastapi_mergen.core.context import current_principal
from fastapi_mergen.errors import LeaseLost
from fastapi_mergen.executors.taskiq.adapter import (
    TaskiqDeliverySink,
    register_taskiq_bridge,
)
from fastapi_mergen.executors.taskiq.envelope import TaskiqHandoffEnvelope
from fastapi_mergen.executors.taskiq.models import TaskiqHandoffRow
from fastapi_mergen.executors.taskiq.store import ExecutingHandoff, TaskiqHandoffStore
from fastapi_mergen.executors.taskiq.worker import TaskiqWorkerBridge
from fastapi_mergen.postgres import PostgresStore
from fastapi_mergen.postgres.executor_schema import install_executor_schema
from fastapi_mergen.postgres.leasing import LeaseRepository
from fastapi_mergen.postgres.relay import SinkDisposition
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.sqlalchemy.models import DeliveryRow
from fastapi_mergen.testing.taskiq_driver import PostgresTaskiqBoundaryDriver
from tests.integration.postgres import ObservedDatabaseClock, ProvisionedDatabase

pytestmark = pytest.mark.integration


async def unused_principal_provider(request: object) -> Principal:
    del request
    raise AssertionError


@pytest.mark.asyncio
async def test_cli_worker_rejects_delayed_handoff_after_parent_reclaim(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn)
    driver: PostgresTaskiqBoundaryDriver | None = None
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_executor_schema(migration_engine, roles=roles)
        driver = await PostgresTaskiqBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        stale, current = await driver.execute_reclaimed_handoff_pair(
            principal=Principal(
                tenant_id=uuid4(),
                subject_id="user:separate-worker-reclaim",
            ),
            delivery_id=uuid4(),
            stale_attempt_id=uuid4(),
        )

        assert stale.status == "dead"
        assert stale.execution_count == 0
        assert current.status == "succeeded"
        assert current.execution_count == 1
        assert stale.delivery_id == current.delivery_id
        assert stale.attempt_id != current.attempt_id
        evidence = await driver.public_evidence()
        assert evidence["taskiq_worker_processes"] == 1
    finally:
        if driver is not None:
            await driver.close()
        else:
            await relay_engine.dispose()
            await app_engine.dispose()
            await migration_engine.dispose()


@pytest.mark.asyncio
async def test_real_taskiq_broker_duplicate_is_fenced_and_context_is_reset(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn)
    app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
    relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
    observed: list[tuple[Principal, str, str]] = []

    @asynccontextmanager
    async def application_session(principal: Principal) -> AsyncIterator[AsyncSession]:
        async with app_sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                {"tenant": str(principal.tenant_id)},
            )
            await session.execute(
                text("SELECT set_config('mergen.subject_id', :subject, true)"),
                {"subject": principal.subject_id},
            )
            yield session

    async def handler(context: EffectContext[object]) -> None:
        bound = current_principal(required=True)
        assert bound is not None
        async with context.application_session() as session:
            tenant = await session.scalar(text("SELECT current_setting('mergen.tenant_id')"))
            subject = await session.scalar(text("SELECT current_setting('mergen.subject_id')"))
        observed.append((bound, str(tenant), str(subject)))

    mergen = Mergen(
        principal_provider=unused_principal_provider,
        store=PostgresStore(),
        handler_session_provider=application_session,
    )
    mergen.route(event_type="invoice.taskiq", route_key="invoice.taskiq").to_handler(
        handler,
        authorization=AuthorizationMode.SNAPSHOT,
        maximum_snapshot_age_seconds=3600,
        retry_policy=RetryPolicy(
            name="taskiq.integration",
            handler_timeout_seconds=2,
            lease_duration_seconds=10,
        ),
    )
    mergen.freeze()
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:taskiq")
    broker = InMemoryBroker()
    store = TaskiqHandoffStore()
    worker = TaskiqWorkerBridge(
        sessions=relay_sessions,
        executor=mergen.handler_executor(),
        store=store,
        execution_timeout=timedelta(seconds=5),
    )
    bridge_task = register_taskiq_bridge(broker, worker)
    sink = TaskiqDeliverySink(
        sessions=relay_sessions,
        task=bridge_task,
        store=store,
    )
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_executor_schema(migration_engine, roles=roles)
        async with (
            app_sessions() as session,
            MergenUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                routes=mergen.routes,
            ) as uow,
        ):
            await uow.emit(Event(type="invoice.taskiq", version=1, data={"invoice": "1"}))
        async with relay_sessions() as session:
            claim = (await LeaseRepository().claim(session, now=datetime.now(UTC)))[0]

        await broker.startup()
        assert await sink.execute(claim) is SinkDisposition.DEFERRED
        await broker.wait_all()

        async with relay_sessions() as session:
            row = await session.scalar(select(TaskiqHandoffRow))
        assert row is not None
        envelope = TaskiqHandoffEnvelope(
            tenant_id=row.tenant_id,
            handoff_id=row.handoff_id,
            delivery_id=row.delivery_id,
            attempt_id=row.attempt_id,
            task_id=row.task_id,
            handoff_token=row.handoff_token,
        )
        await bridge_task.kicker().with_task_id(row.task_id).kiq(envelope.to_dict())
        await broker.wait_all()

        async with relay_sessions() as session:
            handoff = await session.scalar(select(TaskiqHandoffRow))
            delivery = await session.scalar(select(DeliveryRow))
        assert handoff is not None
        assert handoff.state == "succeeded"
        assert handoff.execution_count == 1
        assert delivery is not None
        assert delivery.state == "succeeded"
        assert len(observed) == 1
        assert observed[0] == (principal, str(tenant_id), principal.subject_id)
        assert current_principal(required=False) is None
    finally:
        await broker.shutdown()
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()


@pytest.mark.asyncio
async def test_expired_execution_rejects_stale_finalization(
    test_database: ProvisionedDatabase,
) -> None:
    # The full stale-token path is covered through the same real PostgreSQL rows,
    # without requiring a broker process to be killed by the test runner.
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn)
    app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
    relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
    database_clock = ObservedDatabaseClock()
    leases = LeaseRepository(database_clock=database_clock)
    store = TaskiqHandoffStore(leases=leases, database_clock=database_clock)
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:expiry")

    async def noop(context: EffectContext[object]) -> None:
        del context

    mergen = Mergen(principal_provider=unused_principal_provider, store=PostgresStore())
    mergen.route(event_type="expiry.test", route_key="expiry.test").to_handler(
        noop,
        authorization=AuthorizationMode.SNAPSHOT,
        maximum_snapshot_age_seconds=3600,
        retry_policy=RetryPolicy(
            name="expiry",
            handler_timeout_seconds=10,
            lease_duration_seconds=12,
        ),
    )
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_executor_schema(migration_engine, roles=roles)
        async with (
            app_sessions() as session,
            MergenUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                routes=mergen.routes,
            ) as uow,
        ):
            await uow.emit(Event(type="expiry.test", version=1, data={}))
        started = datetime.now(UTC)
        async with relay_sessions() as session:
            claim = (await leases.claim(session, now=started))[0]
        async with relay_sessions() as session:
            envelope = await store.prepare(session, claim=claim, now=started)
        async with relay_sessions() as session:
            await store.mark_enqueued(session, envelope=envelope, now=started)

        async def claim_execution() -> ExecutingHandoff | None:
            async with relay_sessions() as session:
                return await store.claim_execution(
                    session,
                    envelope=envelope,
                    now=started,
                    execution_timeout=timedelta(seconds=1),
                )

        claimed = await asyncio.gather(claim_execution(), claim_execution())
        executing = next(value for value in claimed if value is not None)
        assert sum(value is not None for value in claimed) == 1
        assert executing is not None
        async with relay_sessions() as session:
            replacement = await store.claim_execution(
                session,
                envelope=envelope,
                now=started + timedelta(seconds=2),
                execution_timeout=timedelta(seconds=1),
            )
        assert replacement is not None
        assert replacement.execution_token != executing.execution_token
        with pytest.raises(LeaseLost):
            async with relay_sessions() as session:
                await store.finalize_success(
                    session,
                    executing=executing,
                    now=started + timedelta(seconds=2),
                )
        async with relay_sessions() as session:
            await store.finalize_success(
                session,
                executing=replacement,
                now=started + timedelta(seconds=2),
            )
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()


@pytest.mark.asyncio
async def test_old_handoff_is_rejected_after_parent_attempt_is_reclaimed(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn)
    app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
    relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
    database_clock = ObservedDatabaseClock()
    leases = LeaseRepository(database_clock=database_clock)
    store = TaskiqHandoffStore(leases=leases, database_clock=database_clock)
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:stale-handoff")

    async def noop(context: EffectContext[object]) -> None:
        del context

    mergen = Mergen(principal_provider=unused_principal_provider, store=PostgresStore())
    mergen.route(event_type="stale.test", route_key="stale.test").to_handler(
        noop,
        authorization=AuthorizationMode.SNAPSHOT,
        maximum_snapshot_age_seconds=3600,
        retry_policy=RetryPolicy(
            name="stale-handoff",
            handler_timeout_seconds=1,
            lease_duration_seconds=3,
        ),
    )
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_executor_schema(migration_engine, roles=roles)
        async with (
            app_sessions() as session,
            MergenUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                routes=mergen.routes,
            ) as uow,
        ):
            await uow.emit(Event(type="stale.test", version=1, data={}))
        started = datetime.now(UTC)
        async with relay_sessions() as session:
            attempt_a = (await leases.claim(session, now=started))[0]
        async with relay_sessions() as session:
            envelope_a = await store.prepare(session, claim=attempt_a, now=started)
        async with relay_sessions() as session:
            await store.mark_enqueued(session, envelope=envelope_a, now=started)

        reclaimed_at = started + timedelta(seconds=4)
        async with relay_sessions() as session:
            assert await leases.reconcile_expired(session, now=reclaimed_at) == 1
        async with relay_sessions() as session:
            attempt_b = (await leases.claim(session, now=reclaimed_at))[0]
        assert attempt_b.lease_token != attempt_a.lease_token
        async with relay_sessions() as session:
            envelope_b = await store.prepare(session, claim=attempt_b, now=reclaimed_at)
        async with relay_sessions() as session:
            await store.mark_enqueued(session, envelope=envelope_b, now=reclaimed_at)

        async with relay_sessions() as session:
            assert (
                await store.claim_execution(
                    session,
                    envelope=envelope_a,
                    now=reclaimed_at,
                    execution_timeout=timedelta(seconds=1),
                )
                is None
            )
        async with relay_sessions() as session:
            executing_b = await store.claim_execution(
                session,
                envelope=envelope_b,
                now=reclaimed_at,
                execution_timeout=timedelta(seconds=1),
            )
        assert executing_b is not None
        assert executing_b.claim.lease_token == attempt_b.lease_token

        async with relay_sessions() as session:
            handoffs = (
                await session.scalars(
                    select(TaskiqHandoffRow).order_by(TaskiqHandoffRow.prepared_at)
                )
            ).all()
        assert [row.state for row in handoffs] == ["dead", "executing"]
        assert [row.execution_count for row in handoffs] == [0, 1]
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()

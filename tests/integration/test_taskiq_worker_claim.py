from __future__ import annotations

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
from fastapi_mergen.executors.taskiq.store import TaskiqHandoffStore
from fastapi_mergen.executors.taskiq.worker import TaskiqWorkerBridge
from fastapi_mergen.postgres import PostgresStore
from fastapi_mergen.postgres.executor_schema import install_executor_schema
from fastapi_mergen.postgres.leasing import LeaseRepository
from fastapi_mergen.postgres.relay import SinkDisposition
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.sqlalchemy.models import DeliveryRow
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration


async def unused_principal_provider(request: object) -> Principal:
    del request
    raise AssertionError


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
    store = TaskiqHandoffStore()
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
            await uow.emit(Event(type="expiry.test", version=1, data={}))
        started = datetime.now(UTC)
        async with relay_sessions() as session:
            claim = (await LeaseRepository().claim(session, now=started))[0]
        async with relay_sessions() as session:
            envelope = await store.prepare(session, claim=claim, now=started)
        async with relay_sessions() as session:
            await store.mark_enqueued(session, envelope=envelope, now=started)
        async with relay_sessions() as session:
            executing = await store.claim_execution(
                session,
                envelope=envelope,
                now=started,
                execution_timeout=timedelta(seconds=1),
            )
        assert executing is not None
        async with relay_sessions() as session:
            assert (
                await store.recover_expired(
                    session,
                    now=started + timedelta(seconds=2),
                )
                == 1
            )
        with pytest.raises(LeaseLost):
            async with relay_sessions() as session:
                await store.finalize_success(
                    session,
                    executing=executing,
                    now=started + timedelta(seconds=2),
                )
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()

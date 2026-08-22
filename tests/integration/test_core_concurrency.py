from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_mergen import (
    AuthorizationMode,
    Event,
    LeaseLost,
    MergenUnitOfWork,
    Principal,
    RetryPolicy,
)
from fastapi_mergen.core.context import current_principal
from fastapi_mergen.core.routing import RouteSpecification
from fastapi_mergen.postgres.leasing import ClaimedDelivery, LeaseRepository
from fastapi_mergen.postgres.relay import PollingRelay, RelayConfig
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.postgres.store import PostgresStore
from fastapi_mergen.sqlalchemy.models import AttemptRow, DeliveryRow, EventRow
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration


def _route(route_key: str = "invoice.render") -> RouteSpecification:
    return RouteSpecification(
        event_type="invoice.created",
        route_key=route_key,
        version=1,
        destination_kind="handler",
        destination_key=route_key,
        required_scopes=(),
        authorization=AuthorizationMode.SNAPSHOT,
        service_policy=None,
        service_capabilities=None,
        maximum_snapshot_age_seconds=300,
        retry_policy=RetryPolicy(
            name="concurrency",
            base_delay_seconds=0,
            maximum_delay_seconds=0,
            handler_timeout_seconds=1,
            lease_duration_seconds=2,
        ),
    )


async def _emit(
    sessions: async_sessionmaker[AsyncSession],
    principal: Principal,
    *,
    dedupe_key: str | None = None,
    routes: tuple[RouteSpecification, ...] | None = None,
) -> UUID:
    async with sessions() as session:
        uow = MergenUnitOfWork(
            session=session,
            principal=principal,
            store=PostgresStore(),
            routes=routes or (_route(),),
        )
        async with uow:
            record = await uow.emit(
                Event(type="invoice.created", version=1, data={"invoice_id": "inv-1"}),
                dedupe_namespace="concurrent" if dedupe_key is not None else None,
                dedupe_key=dedupe_key,
            )
        return record.event_id


@pytest.mark.asyncio
async def test_uow_cancellation_rolls_back_and_cleans_context(
    test_database: ProvisionedDatabase,
) -> None:
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    principal = Principal(tenant_id=uuid4(), subject_id="user:cancelled")
    try:
        await install_core_schema(migration, roles=roles)
        sessions = async_sessionmaker(application, expire_on_commit=False)

        async def cancelled_operation() -> None:
            async with sessions() as session:
                uow = MergenUnitOfWork(
                    session=session,
                    principal=principal,
                    store=PostgresStore(),
                    routes=(_route(),),
                )
                async with uow:
                    await uow.emit(
                        Event(type="invoice.created", version=1, data={"invoice_id": "cancel"})
                    )
                    raise asyncio.CancelledError

        task = asyncio.create_task(cancelled_operation())
        with pytest.raises(asyncio.CancelledError):
            await task
        assert current_principal(required=False) is None

        async with sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                {"tenant": str(principal.tenant_id)},
            )
            event_count = await session.scalar(select(func.count()).select_from(EventRow))
        assert event_count == 0
    finally:
        await application.dispose()
        await migration.dispose()


@pytest.mark.asyncio
async def test_concurrent_dedupe_and_claim_races_converge(
    test_database: ProvisionedDatabase,
) -> None:
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay = create_async_engine(test_database.relay_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    try:
        await install_core_schema(migration, roles=roles)
        app_sessions = async_sessionmaker(application, expire_on_commit=False)
        relay_sessions = async_sessionmaker(relay, expire_on_commit=False)
        principal = Principal(tenant_id=uuid4(), subject_id="user:race")

        first, second = await asyncio.gather(
            _emit(app_sessions, principal, dedupe_key="same-key"),
            _emit(app_sessions, principal, dedupe_key="same-key"),
        )
        assert first == second
        for index in range(9):
            await _emit(app_sessions, principal, dedupe_key=f"key-{index}")

        leases = LeaseRepository()

        async def claim() -> tuple[UUID, ...]:
            async with relay_sessions() as session:
                claimed = await leases.claim(
                    session,
                    now=datetime.now(UTC),
                    batch_size=10,
                    per_tenant=10,
                )
            return tuple(item.delivery.delivery_id for item in claimed)

        left, right = await asyncio.gather(claim(), claim())
        assert len(left) + len(right) == 10
        assert set(left).isdisjoint(right)
    finally:
        await relay.dispose()
        await application.dispose()
        await migration.dispose()


@pytest.mark.asyncio
async def test_claim_fairness_and_expired_lease_fencing(
    test_database: ProvisionedDatabase,
) -> None:
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay = create_async_engine(test_database.relay_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    try:
        await install_core_schema(migration, roles=roles)
        app_sessions = async_sessionmaker(application, expire_on_commit=False)
        relay_sessions = async_sessionmaker(relay, expire_on_commit=False)
        first_tenant = Principal(tenant_id=uuid4(), subject_id="user:first")
        second_tenant = Principal(tenant_id=uuid4(), subject_id="user:second")
        for _index in range(12):
            await _emit(app_sessions, first_tenant)
        await _emit(app_sessions, second_tenant)

        leases = LeaseRepository()
        claimed_at = datetime.now(UTC)
        async with relay_sessions() as session:
            claims = await leases.claim(
                session,
                now=claimed_at,
                batch_size=10,
                per_tenant=1,
            )
        assert {claim.delivery.tenant_id for claim in claims} == {
            first_tenant.tenant_id,
            second_tenant.tenant_id,
        }

        stale = next(
            claim for claim in claims if claim.delivery.tenant_id == second_tenant.tenant_id
        )
        after_expiry = claimed_at + timedelta(seconds=3)
        async with relay_sessions() as session:
            assert await leases.reconcile_expired(session, now=after_expiry) == 2
        async with relay_sessions() as session:
            reclaimed = await leases.claim(
                session,
                now=after_expiry,
                batch_size=2,
                per_tenant=1,
            )
        current = next(
            claim for claim in reclaimed if claim.delivery.delivery_id == stale.delivery.delivery_id
        )
        assert current.lease_token != stale.lease_token
        async with relay_sessions() as session:
            with pytest.raises(LeaseLost):
                await leases.succeed(session, stale, now=after_expiry)
        async with relay_sessions() as session:
            abandoned = await session.scalar(
                select(func.count())
                .select_from(AttemptRow)
                .where(AttemptRow.outcome == "abandoned")
            )
        assert abandoned == 2
    finally:
        await relay.dispose()
        await application.dispose()
        await migration.dispose()


@pytest.mark.asyncio
async def test_relay_never_leases_more_than_immediate_execution_capacity(
    test_database: ProvisionedDatabase,
) -> None:
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )

    class SuccessfulSink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            del claim

    try:
        await install_core_schema(migration, roles=roles)
        app_sessions = async_sessionmaker(application, expire_on_commit=False)
        relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
        principal = Principal(tenant_id=uuid4(), subject_id="user:relay-bound")
        for index in range(6):
            await _emit(app_sessions, principal, dedupe_key=f"relay-{index}")

        relay = PollingRelay(
            sessions=relay_sessions,
            sink=SuccessfulSink(),
            config=RelayConfig(batch_size=6, per_tenant=6, concurrency=2),
        )
        assert await relay.run_once() == 2

        async with relay_sessions() as session:
            states = dict(
                (
                    await session.execute(
                        select(DeliveryRow.state, func.count())
                        .group_by(DeliveryRow.state)
                        .order_by(DeliveryRow.state)
                    )
                ).all()
            )
        assert states == {"pending": 4, "succeeded": 2}
    finally:
        await relay_engine.dispose()
        await application.dispose()
        await migration.dispose()


@pytest.mark.asyncio
async def test_fanout_failure_rolls_back_business_and_event_rows(
    test_database: ProvisionedDatabase,
) -> None:
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    tenant = uuid4()
    try:
        await install_core_schema(migration, roles=roles)
        async with migration.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE public.atomic_business "
                    "(tenant_id uuid NOT NULL, business_key text NOT NULL)"
                )
            )
            await connection.execute(
                text("ALTER TABLE public.atomic_business ENABLE ROW LEVEL SECURITY")
            )
            await connection.execute(
                text("ALTER TABLE public.atomic_business FORCE ROW LEVEL SECURITY")
            )
            await connection.execute(
                text(
                    f"CREATE POLICY atomic_tenant ON public.atomic_business TO {roles.application} "
                    "USING (tenant_id = "
                    "nullif(current_setting('mergen.tenant_id', true), '')::uuid) "
                    "WITH CHECK (tenant_id = "
                    "nullif(current_setting('mergen.tenant_id', true), '')::uuid)"
                )
            )
            await connection.execute(
                text(f"GRANT SELECT, INSERT ON public.atomic_business TO {roles.application}")
            )

        sessions = async_sessionmaker(application, expire_on_commit=False)
        principal = Principal(tenant_id=tenant, subject_id="user:rollback")
        routes = (_route(), _route("invoice.archive"))

        class ConstantUUIDs:
            def __init__(self) -> None:
                self.value = uuid4()

            def new_uuid(self) -> UUID:
                return self.value

        async def publish_invalid_fanout() -> None:
            async with sessions() as session:
                uow = MergenUnitOfWork(
                    session=session,
                    principal=principal,
                    store=PostgresStore(),
                    routes=routes,
                    uuid_source=ConstantUUIDs(),
                )
                async with uow:
                    await session.execute(
                        text(
                            "INSERT INTO public.atomic_business(tenant_id, business_key) "
                            "VALUES (:tenant, 'rollback')"
                        ),
                        {"tenant": tenant},
                    )
                    await uow.emit(
                        Event(type="invoice.created", version=1, data={"invoice_id": "inv"})
                    )

        with pytest.raises(IntegrityError):
            await publish_invalid_fanout()

        async with sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                {"tenant": str(tenant)},
            )
            business_count = await session.scalar(
                text("SELECT count(*) FROM public.atomic_business")
            )
            event_count = await session.scalar(select(func.count()).select_from(EventRow))
            delivery_count = await session.scalar(select(func.count()).select_from(DeliveryRow))
        assert (business_count, event_count, delivery_count) == (0, 0, 0)
    finally:
        await application.dispose()
        await migration.dispose()

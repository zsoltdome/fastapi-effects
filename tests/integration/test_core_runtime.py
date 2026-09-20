from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_effects import (
    AuthorizationMode,
    DedupeConflict,
    EffectContext,
    Event,
    FastAPIEffects,
    FastAPIEffectsUnitOfWork,
    LeaseLost,
    Principal,
    RetryPolicy,
)
from fastapi_effects.postgres import PostgresStore
from fastapi_effects.postgres.diagnostics import inspect_runtime_database
from fastapi_effects.postgres.leasing import LeaseRepository
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.sqlalchemy.models import DeliveryRow, EventRow
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration


async def principal_provider(request: object) -> Principal:
    del request
    raise AssertionError


async def handler(context: EffectContext[object]) -> None:
    del context


@pytest.mark.asyncio
async def test_atomic_publish_dedupe_rls_and_fenced_delivery(
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
    try:
        await install_core_schema(migration_engine, roles=roles)
        report = await inspect_runtime_database(
            app_engine,
            expected_role=test_database.app_role,
            roles=roles,
        )
        assert report.healthy, report.checks
        app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
        relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
        fastapi_effects = FastAPIEffects(
            principal_provider=principal_provider, store=PostgresStore()
        )
        fastapi_effects.route(
            event_type="invoice.created",
            route_key="invoice.render",
        ).to_handler(
            handler,
            authorization=AuthorizationMode.SNAPSHOT,
            maximum_snapshot_age_seconds=300,
            retry_policy=RetryPolicy(
                name="integration",
                handler_timeout_seconds=1,
                lease_duration_seconds=10,
            ),
        )
        fastapi_effects.freeze()
        tenant = uuid4()
        principal = Principal(tenant_id=tenant, subject_id="user:integration")

        async with app_sessions() as session:
            first_uow = FastAPIEffectsUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                routes=fastapi_effects.routes,
            )
            async with first_uow:
                first = await first_uow.emit(
                    Event(type="invoice.created", version=1, data={"invoice_id": "inv-1"}),
                    dedupe_namespace="invoice-create",
                    dedupe_key="request-1",
                )
            second_uow = FastAPIEffectsUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                routes=fastapi_effects.routes,
            )
            async with second_uow:
                second = await second_uow.emit(
                    Event(type="invoice.created", version=1, data={"invoice_id": "inv-1"}),
                    dedupe_namespace="invoice-create",
                    dedupe_key="request-1",
                )
            assert second.event_id == first.event_id

            conflict_uow = FastAPIEffectsUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                routes=fastapi_effects.routes,
            )
            with pytest.raises(DedupeConflict):
                async with conflict_uow:
                    await conflict_uow.emit(
                        Event(
                            type="invoice.created",
                            version=1,
                            data={"invoice_id": "different"},
                        ),
                        dedupe_namespace="invoice-create",
                        dedupe_key="request-1",
                    )

            async with session.begin():
                await session.execute(
                    text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
                    {"tenant": str(tenant)},
                )
                assert await session.scalar(select(func.count()).select_from(EventRow)) == 1
                assert await session.scalar(select(func.count()).select_from(DeliveryRow)) == 1
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
                    {"tenant": str(uuid4())},
                )
                assert await session.scalar(select(func.count()).select_from(EventRow)) == 0

        leases = LeaseRepository()
        now = datetime.now(UTC)
        async with relay_sessions() as session:
            claims = await leases.claim(session, now=now)
        assert len(claims) == 1
        claim = claims[0]
        assert claim.delivery.event_id == first.event_id
        async with relay_sessions() as session:
            await leases.succeed(session, claim, now=datetime.now(UTC))
        async with relay_sessions() as session:
            with pytest.raises(LeaseLost):
                await leases.succeed(session, claim, now=datetime.now(UTC))
        async with relay_sessions() as session:
            replay = await leases.replay(
                session,
                tenant_id=tenant,
                delivery_id=claim.delivery.delivery_id,
                actor="operator:integration",
                reason="manual.recovery",
                now=datetime.now(UTC),
            )
        assert replay.delivery_id != claim.delivery.delivery_id
        assert replay.replay_of == claim.delivery.delivery_id
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from fastapi_mergen import (
    AuthorizationMode,
    Event,
    MergenUnitOfWork,
    Principal,
    RetryPolicy,
)
from fastapi_mergen.core.context import current_principal
from fastapi_mergen.core.routing import RouteSpecification
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.postgres.store import PostgresStore
from fastapi_mergen.sqlalchemy.models import DeliveryRow, EventRow
from tests.integration.postgres import ProvisionedDatabase, sqlalchemy_async_dsn

pytestmark = [pytest.mark.integration, pytest.mark.chaos]


def _database_dsn(admin_dsn: str, database: str) -> str:
    parsed = urlsplit(admin_dsn)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", parsed.query, ""))


def _route() -> RouteSpecification:
    return RouteSpecification(
        event_type="chaos.connection",
        route_key="chaos.connection",
        version=1,
        destination_kind="handler",
        destination_key="chaos.connection",
        required_scopes=(),
        authorization=AuthorizationMode.SNAPSHOT,
        service_policy=None,
        service_capabilities=None,
        maximum_snapshot_age_seconds=300,
        retry_policy=RetryPolicy(
            name="chaos.connection",
            handler_timeout_seconds=1,
            lease_duration_seconds=10,
        ),
    )


async def _terminate_backend(admin: AsyncEngine, backend_pid: int) -> None:
    async with admin.connect() as connection:
        terminated = await connection.scalar(
            text("SELECT pg_terminate_backend(:backend_pid)"),
            {"backend_pid": backend_pid},
        )
    assert terminated is True


async def _write_effect(
    sessions: async_sessionmaker,
    principal: Principal,
    *,
    business_key: str,
    admin: AsyncEngine | None,
) -> tuple[UUID, int]:
    async with sessions() as session:
        uow = MergenUnitOfWork(
            session=session,
            principal=principal,
            store=PostgresStore(),
            routes=(_route(),),
        )
        async with uow:
            await session.execute(
                text(
                    "INSERT INTO public.chaos_business(tenant_id, business_key) "
                    "VALUES (:tenant, :business_key)"
                ),
                {"tenant": principal.tenant_id, "business_key": business_key},
            )
            event = await uow.emit(
                Event(
                    type="chaos.connection",
                    version=1,
                    data={"business_key": business_key},
                )
            )
            backend_pid = int(await session.scalar(text("SELECT pg_backend_pid()")) or 0)
            if admin is not None:
                await _terminate_backend(admin, backend_pid)
        return event.event_id, backend_pid


@pytest.mark.asyncio
async def test_connection_loss_rolls_back_uncommitted_work_and_preserves_committed_intent(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(
        test_database.app_sqlalchemy_dsn,
        pool_pre_ping=True,
    )
    admin = create_async_engine(
        sqlalchemy_async_dsn(_database_dsn(test_database.admin_dsn, test_database.database)),
        pool_pre_ping=True,
    )
    sessions = async_sessionmaker(application, expire_on_commit=False)
    principal = Principal(tenant_id=uuid4(), subject_id="chaos:connection-loss")
    try:
        await install_core_schema(migration, roles=roles)
        async with migration.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE public.chaos_business("
                    "tenant_id uuid NOT NULL, business_key text NOT NULL, "
                    "PRIMARY KEY (tenant_id, business_key))"
                )
            )
            await connection.execute(text("REVOKE ALL ON public.chaos_business FROM PUBLIC"))
            await connection.execute(
                text(f"GRANT SELECT, INSERT ON public.chaos_business TO {test_database.app_role}")
            )

        with pytest.raises(DBAPIError):
            await _write_effect(
                sessions,
                principal,
                business_key="uncommitted",
                admin=admin,
            )
        assert current_principal(required=False) is None
        async with migration.connect() as connection:
            business_count = await connection.scalar(
                text("SELECT count(*) FROM public.chaos_business")
            )
            event_count = await connection.scalar(select(func.count()).select_from(EventRow))
        assert business_count == 0
        assert event_count == 0

        committed_event_id, committed_backend_pid = await _write_effect(
            sessions,
            principal,
            business_key="committed",
            admin=None,
        )
        await _terminate_backend(admin, committed_backend_pid)

        async with sessions() as session, session.begin():
            assert (
                await session.scalar(
                    text("SELECT nullif(current_setting('mergen.tenant_id', true), '')")
                )
                is None
            )
            await session.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                {"tenant": str(principal.tenant_id)},
            )
            restored_event_ids = tuple((await session.scalars(select(EventRow.event_id))).all())
            delivery_count = await session.scalar(select(func.count()).select_from(DeliveryRow))
        assert restored_event_ids == (committed_event_id,)
        assert delivery_count == 1
        async with migration.connect() as connection:
            business_keys = tuple(
                (
                    await connection.scalars(text("SELECT business_key FROM public.chaos_business"))
                ).all()
            )
        assert business_keys == ("committed",)
    finally:
        await admin.dispose()
        await application.dispose()
        await migration.dispose()

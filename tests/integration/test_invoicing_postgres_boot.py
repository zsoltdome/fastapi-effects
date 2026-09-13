from __future__ import annotations

from datetime import UTC, datetime

import pytest
from examples.invoicing.app.auth import DEMO_AUTHORIZATION, DEMO_TENANT_ID
from examples.invoicing.app.db import get_async_session
from examples.invoicing.app.main import app
from examples.invoicing.app.mergen_config import mergen
from examples.invoicing.app.models import Base, InvoiceRender
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_mergen.postgres.leasing import LeaseRepository
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.sqlalchemy.models import DeliveryRow
from tests.integration.postgres import ObservedDatabaseClock, ProvisionedDatabase

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_reference_app_boots_with_disposable_postgres(
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERGEN_EXAMPLE_DATABASE_URL", test_database.app_sqlalchemy_dsn)
    async with app.router.lifespan_context(app):
        session_generator = get_async_session()
        session = await anext(session_generator)
        try:
            assert await session.scalar(text("SELECT 1")) == 1
            assert "/invoices" in app.openapi()["paths"]
        finally:
            await session_generator.aclose()


@pytest.mark.asyncio
async def test_authenticated_invoice_reaches_tenant_bound_handler(
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERGEN_EXAMPLE_DATABASE_URL", test_database.app_sqlalchemy_dsn)
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    try:
        await install_core_schema(migration_engine, roles=roles)
        async with migration_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            for table in ("invoice", "invoice_renders"):
                await connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                await connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
                await connection.execute(
                    text(
                        f"CREATE POLICY {table}_tenant ON {table} "
                        f"FOR ALL TO {test_database.app_role} "
                        "USING (tenant_id = nullif(current_setting('mergen.tenant_id', true), "
                        "'')::uuid) WITH CHECK (tenant_id = "
                        "nullif(current_setting('mergen.tenant_id', true), '')::uuid)"
                    )
                )
                await connection.execute(
                    text(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {test_database.app_role}")
                )

        relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client,
        ):
            response = await client.post(
                "/invoices",
                json={
                    "customer_id": "22222222-2222-4222-8222-222222222222",
                    "amount": "10.50",
                    "currency": "EUR",
                },
                headers={
                    "authorization": DEMO_AUTHORIZATION,
                    "x-tenant-id": str(DEMO_TENANT_ID),
                },
            )
            assert response.status_code == 201, response.text
            invoice_id = response.json()["id"]

            # Exercise the at-least-once crash gap: the consumer transaction
            # commits, relay finalization is lost, and the same business effect
            # completes safely on the replacement attempt.
            leases = LeaseRepository(database_clock=ObservedDatabaseClock())
            async with relay_sessions() as session:
                first = (await leases.claim(session, now=datetime.now(UTC)))[0]
            await mergen.handler_executor().execute(first)
            assert first.delivery.lease_expires_at is not None
            retry_at = first.delivery.lease_expires_at
            async with relay_sessions() as session:
                assert await leases.reconcile_expired(session, now=retry_at) == 1
            async with relay_sessions() as session:
                second = (await leases.claim(session, now=retry_at))[0]
            assert second.delivery.delivery_id == first.delivery.delivery_id
            assert second.attempt.attempt_id != first.attempt.attempt_id
            await mergen.handler_executor().execute(second)
            async with relay_sessions() as session:
                await leases.succeed(session, second, now=retry_at)

        app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
        async with app_sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                {"tenant": str(DEMO_TENANT_ID)},
            )
            render = await session.scalar(
                select(InvoiceRender).where(InvoiceRender.invoice_id == invoice_id)
            )
            render_count = await session.scalar(select(func.count()).select_from(InvoiceRender))
            delivery_state = await session.scalar(select(DeliveryRow.state))
        assert render is not None
        assert render.delivery_id == first.delivery.delivery_id
        assert render_count == 1
        assert delivery_state == "succeeded"
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()

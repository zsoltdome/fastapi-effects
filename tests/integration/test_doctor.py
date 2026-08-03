from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from fastapi_mergen.postgres.diagnostics import inspect_runtime_database
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from tests.integration.postgres import ProvisionedDatabase, sqlalchemy_async_dsn

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_doctor_probes_application_relay_and_unsafe_role(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay = create_async_engine(test_database.relay_sqlalchemy_dsn)
    unsafe = create_async_engine(sqlalchemy_async_dsn(test_database.misconfigured_dsn))
    try:
        await install_core_schema(migration, roles=roles)
        async with migration.begin() as connection:
            await connection.execute(
                text("CREATE TABLE public.doctor_business (tenant_id uuid NOT NULL)")
            )
            await connection.execute(text("REVOKE ALL ON public.doctor_business FROM PUBLIC"))
            await connection.execute(
                text(f"GRANT SELECT ON public.doctor_business TO {test_database.app_role}")
            )
            await connection.execute(
                text(f"GRANT USAGE ON SCHEMA fastapi_mergen TO {test_database.misconfigured_role}")
            )
            await connection.execute(
                text(
                    "GRANT SELECT ON fastapi_mergen.schema_revision, "
                    "fastapi_mergen.events, fastapi_mergen.deliveries, "
                    f"fastapi_mergen.attempts TO {test_database.misconfigured_role}"
                )
            )

        app_report = await inspect_runtime_database(
            application,
            expected_role=test_database.app_role,
            roles=roles,
        )
        assert app_report.healthy, app_report.checks
        assert {
            "context.rollback_cleanup",
            "context.commit_cleanup",
            "context.pool_cleanup",
        }.issubset({check.code for check in app_report.checks})

        relay_report = await inspect_runtime_database(
            relay,
            expected_role=test_database.relay_role,
            application_table="public.doctor_business",
            roles=roles,
        )
        assert relay_report.healthy, relay_report.checks

        unsafe_report = await inspect_runtime_database(
            unsafe,
            expected_role=test_database.misconfigured_role,
            roles=roles,
        )
        assert not unsafe_report.healthy
        assert any(
            check.code == "role.no_bypassrls" and check.status.value == "fail"
            for check in unsafe_report.checks
        )
    finally:
        await unsafe.dispose()
        await relay.dispose()
        await application.dispose()
        await migration.dispose()

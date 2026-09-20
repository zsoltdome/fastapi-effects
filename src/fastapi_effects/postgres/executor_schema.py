"""Taskiq handoff schema installation, RLS, grants, and compatibility."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_effects.errors import SchemaRevisionMismatch
from fastapi_effects.executors.taskiq.models import TASKIQ_TABLES
from fastapi_effects.postgres.rls import TENANT_EXPRESSION
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.sqlalchemy.models import SCHEMA

EXECUTOR_SCHEMA_REVISION = 1


def executor_schema_sql(roles: RuntimeRoles | None = None) -> tuple[str, ...]:
    configured = roles or RuntimeRoles()
    qualified = f"{SCHEMA}.taskiq_handoffs"
    return (
        f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS taskiq_handoffs_application_tenant ON {qualified}",
        (
            f"CREATE POLICY taskiq_handoffs_application_tenant ON {qualified} "
            f"FOR SELECT TO {configured.application} USING ({TENANT_EXPRESSION})"
        ),
        f"DROP POLICY IF EXISTS taskiq_handoffs_relay_control ON {qualified}",
        (
            f"CREATE POLICY taskiq_handoffs_relay_control ON {qualified} "
            f"FOR ALL TO {configured.relay} USING (true) WITH CHECK (true)"
        ),
        f"DROP POLICY IF EXISTS taskiq_handoffs_migration_control ON {qualified}",
        (
            f"CREATE POLICY taskiq_handoffs_migration_control ON {qualified} "
            f"FOR ALL TO {configured.migration} USING (true) WITH CHECK (true)"
        ),
        f"GRANT SELECT ON {qualified} TO {configured.application}",
        f"GRANT SELECT, INSERT, UPDATE ON {qualified} TO {configured.relay}",
    )


async def install_executor_schema(
    engine: AsyncEngine,
    *,
    roles: RuntimeRoles | None = None,
) -> None:
    configured = roles or RuntimeRoles()
    async with engine.begin() as connection:
        for table in TASKIQ_TABLES:
            await connection.run_sync(table.create, checkfirst=True)
        await connection.execute(
            text(
                f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
                "VALUES ('executor.taskiq', :revision, CURRENT_TIMESTAMP) "
                "ON CONFLICT (component) DO UPDATE SET revision = EXCLUDED.revision, "
                "installed_at = EXCLUDED.installed_at"
            ),
            {"revision": EXECUTOR_SCHEMA_REVISION},
        )
        for statement in executor_schema_sql(configured):
            await connection.execute(text(statement))


async def check_executor_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        actual = await connection.scalar(
            text(
                f"SELECT revision FROM {SCHEMA}.schema_revision WHERE component = 'executor.taskiq'"
            )
        )
    if actual != EXECUTOR_SCHEMA_REVISION:
        raise SchemaRevisionMismatch(
            component="executor.taskiq",
            expected=EXECUTOR_SCHEMA_REVISION,
            actual=0 if actual is None else int(actual),
        )


__all__ = [
    "EXECUTOR_SCHEMA_REVISION",
    "check_executor_schema",
    "executor_schema_sql",
    "install_executor_schema",
]

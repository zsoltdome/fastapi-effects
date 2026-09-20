"""Programmatic async schema installation and compatibility checks."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_effects.errors import SchemaRevisionMismatch
from fastapi_effects.postgres.rls import rls_sql
from fastapi_effects.postgres.roles import RuntimeRoles, create_role_sql
from fastapi_effects.sqlalchemy.models import CORE_TABLES, SCHEMA

CORE_SCHEMA_REVISION = 1


async def install_core_schema(
    engine: AsyncEngine,
    *,
    roles: RuntimeRoles | None = None,
    create_roles: bool = False,
) -> None:
    """Install reviewed core objects using migration-owner credentials."""
    configured = roles or RuntimeRoles()
    async with engine.begin() as connection:
        if create_roles:
            for role in (
                configured.migration,
                configured.application,
                configured.relay,
            ):
                await connection.execute(text(create_role_sql(role)))
        await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        for table in CORE_TABLES:
            await connection.run_sync(table.create, checkfirst=True)
        await connection.execute(
            text(
                f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
                "VALUES ('core', :revision, CURRENT_TIMESTAMP) ON CONFLICT (component) "
                "DO UPDATE SET revision = EXCLUDED.revision, "
                "installed_at = EXCLUDED.installed_at"
            ),
            {"revision": CORE_SCHEMA_REVISION},
        )
        for statement in rls_sql(configured):
            await connection.execute(text(statement))
        await connection.execute(text(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC"))
        await connection.execute(
            text(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {configured.application}, {configured.relay}")
        )
        await connection.execute(
            text(
                f"GRANT SELECT, INSERT ON {SCHEMA}.events, {SCHEMA}.deliveries "
                f"TO {configured.application}"
            )
        )
        await connection.execute(
            text(f"GRANT SELECT ON {SCHEMA}.attempts TO {configured.application}")
        )
        await connection.execute(text(f"GRANT SELECT ON {SCHEMA}.events TO {configured.relay}"))
        await connection.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE ON {SCHEMA}.deliveries, "
                f"{SCHEMA}.attempts TO {configured.relay}"
            )
        )
        await connection.execute(
            text(
                f"GRANT SELECT ON {SCHEMA}.schema_revision "
                f"TO {configured.application}, {configured.relay}"
            )
        )


async def check_core_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        actual = await connection.scalar(
            text(f"SELECT revision FROM {SCHEMA}.schema_revision WHERE component = 'core'")
        )
    if actual != CORE_SCHEMA_REVISION:
        raise SchemaRevisionMismatch(
            component="core",
            expected=CORE_SCHEMA_REVISION,
            actual=0 if actual is None else int(actual),
        )


async def drop_core_schema(engine: AsyncEngine) -> None:
    """Drop only the authoritative FastAPIEffects schema (primarily for isolated tests)."""
    async with engine.begin() as connection:
        await connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))


__all__ = [
    "CORE_SCHEMA_REVISION",
    "check_core_schema",
    "drop_core_schema",
    "install_core_schema",
]

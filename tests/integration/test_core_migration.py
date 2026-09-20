from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine

from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import check_core_schema
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration

MIGRATIONS = (
    Path(__file__).resolve().parents[2] / "src" / "fastapi_effects" / "postgres" / "migrations"
)


def _run_revision(connection: Connection, revision: str, roles: RuntimeRoles) -> None:
    configuration = Config(str(MIGRATIONS / "alembic.ini"))
    configuration.set_main_option("script_location", str(MIGRATIONS))
    configuration.attributes["connection"] = connection
    configuration.attributes["runtime_roles"] = roles
    configuration.attributes["create_runtime_roles"] = False
    if revision == "base":
        command.downgrade(configuration, revision)
    else:
        command.upgrade(configuration, revision)


@pytest.mark.asyncio
async def test_core_alembic_upgrade_downgrade_round_trip(
    test_database: ProvisionedDatabase,
) -> None:
    engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_run_revision, "head", roles)
        await check_core_schema(engine)

        async with engine.begin() as connection:
            await connection.run_sync(_run_revision, "base", roles)
            schema_exists = await connection.scalar(
                text("SELECT to_regnamespace('fastapi_effects')")
            )
        assert schema_exists is None

        async with engine.begin() as connection:
            await connection.run_sync(_run_revision, "head", roles)
        await check_core_schema(engine)
    finally:
        await engine.dispose()

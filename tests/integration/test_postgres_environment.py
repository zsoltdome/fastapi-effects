from __future__ import annotations

from typing import Any

import pytest

from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration


async def connect(dsn: str) -> Any:
    import asyncpg

    return await asyncpg.connect(dsn)


@pytest.mark.asyncio
async def test_fixture_exposes_expected_role_flags(test_database: ProvisionedDatabase) -> None:
    for dsn, expected_user, bypass in (
        (test_database.migration_dsn, test_database.migration_role, False),
        (test_database.app_dsn, test_database.app_role, False),
        (test_database.relay_dsn, test_database.relay_role, False),
        (test_database.misconfigured_dsn, test_database.misconfigured_role, True),
    ):
        connection = await connect(dsn)
        try:
            row = await connection.fetchrow(
                "SELECT current_user AS name, current_database() AS database, "
                "rolsuper, rolbypassrls FROM pg_catalog.pg_roles WHERE rolname = current_user"
            )
            assert row["name"] == expected_user
            assert row["database"] == test_database.database
            assert row["rolsuper"] is False
            assert row["rolbypassrls"] is bypass
        finally:
            await connection.close()


@pytest.mark.asyncio
async def test_only_migration_owner_can_create_application_schema(
    test_database: ProvisionedDatabase,
) -> None:
    owner = await connect(test_database.migration_dsn)
    try:
        await owner.execute("CREATE SCHEMA application AUTHORIZATION CURRENT_USER")
        await owner.execute("CREATE TABLE application.private_value (id integer PRIMARY KEY)")
        await owner.execute("INSERT INTO application.private_value VALUES (1)")
    finally:
        await owner.close()

    for dsn in (test_database.app_dsn, test_database.relay_dsn):
        connection = await connect(dsn)
        try:
            with pytest.raises(Exception, match="permission denied"):
                await connection.fetchval("SELECT id FROM application.private_value")
        finally:
            await connection.close()

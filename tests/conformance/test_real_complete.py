from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from fastapi_effects.conformance import (
    CertificationProfile,
    ConformanceRunner,
    RunnerConfiguration,
)
from fastapi_effects.postgres.command_schema import install_command_schema
from fastapi_effects.postgres.executor_schema import install_executor_schema
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.postgres.webhook_schema import install_webhook_schema
from fastapi_effects.testing.complete_driver import PostgresCompleteBoundaryDriver
from tests.integration.postgres import ProvisionedDatabase

pytestmark = [pytest.mark.integration, pytest.mark.conformance]


@pytest.mark.asyncio
async def test_real_cumulative_adapter_certifies_complete_profile(
    test_database: ProvisionedDatabase,
) -> None:
    redis_url = os.getenv("FASTAPI_EFFECTS_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("FASTAPI_EFFECTS_TEST_REDIS_URL is required for real Taskiq certification.")
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
        await install_webhook_schema(migration_engine, roles=roles)
        await install_executor_schema(migration_engine, roles=roles)
        await install_command_schema(migration_engine, roles=roles)
        driver = await PostgresCompleteBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
            redis_url=redis_url,
        )
        report = await ConformanceRunner(
            RunnerConfiguration(profile=CertificationProfile.COMPLETE)
        ).run(driver)
        failures = [
            f"{result.check_id}: {result.status.value} ({result.exception_type})"
            for result in report.results
            if result.status.value not in {"passed", "not_applicable"}
        ]
        assert report.certified, "\n".join(failures)
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()

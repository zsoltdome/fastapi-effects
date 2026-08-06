from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from fastapi_mergen.conformance import (
    CertificationProfile,
    ConformanceRunner,
    RunnerConfiguration,
)
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.testing.postgres_driver import PostgresBoundaryDriver
from tests.integration.postgres import ProvisionedDatabase

pytestmark = [pytest.mark.integration, pytest.mark.conformance]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile",
    [
        CertificationProfile.CORE,
        CertificationProfile.DELIVERY,
        CertificationProfile.SECURITY,
    ],
)
async def test_real_postgres_runtime_certifies_core_profiles(
    test_database: ProvisionedDatabase,
    profile: CertificationProfile,
) -> None:
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
        driver = await PostgresBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        report = await ConformanceRunner(RunnerConfiguration(profile=profile)).run(driver)
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

#!/usr/bin/env python3
"""Generate cumulative certification evidence against isolated real services."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.ext.asyncio import create_async_engine
from tests.integration.postgres import provision_test_database

from fastapi_mergen.conformance import (
    CertificationProfile,
    ConformanceRunner,
    RunnerConfiguration,
)
from fastapi_mergen.conformance.reporters import ReportFormat, render_report
from fastapi_mergen.postgres.command_schema import install_command_schema
from fastapi_mergen.postgres.executor_schema import install_executor_schema
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.postgres.webhook_schema import install_webhook_schema
from fastapi_mergen.testing.complete_driver import PostgresCompleteBoundaryDriver


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Real certification requires {name}.")
    return value


async def _generate() -> tuple[bool, str, str]:
    admin_dsn = _required_environment("MERGEN_TEST_ADMIN_DSN")
    redis_url = _required_environment("MERGEN_TEST_REDIS_URL")
    async with provision_test_database(admin_dsn) as database:
        migration_engine = create_async_engine(database.migration_sqlalchemy_dsn)
        app_engine = create_async_engine(database.app_sqlalchemy_dsn)
        relay_engine = create_async_engine(database.relay_sqlalchemy_dsn)
        roles = RuntimeRoles(
            migration=database.migration_role,
            application=database.app_role,
            relay=database.relay_role,
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
            manifest_json = driver.manifest.to_json() + "\n"
            report = await ConformanceRunner(
                RunnerConfiguration(profile=CertificationProfile.COMPLETE)
            ).run(driver)
            return report.certified, manifest_json, render_report(report, ReportFormat.JSON)
        finally:
            await relay_engine.dispose()
            await app_engine.dispose()
            await migration_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    certified, manifest_json, report_json = asyncio.run(_generate())
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(manifest_json, encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_json, encoding="utf-8")
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())

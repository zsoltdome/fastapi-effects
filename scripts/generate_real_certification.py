#!/usr/bin/env python3
"""Generate cumulative certification evidence against isolated real services."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.ext.asyncio import create_async_engine
from tests.integration.postgres import provision_test_database

import fastapi_mergen
from fastapi_mergen.conformance import (
    CertificationProfile,
    ConformanceRunner,
    RunnerConfiguration,
)
from fastapi_mergen.conformance.reporters import ReportFormat, render_report
from fastapi_mergen.conformance.safety import JsonValue
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


_DIGEST = re.compile(r"^[0-9a-f]{64}$")


async def _generate(artifact_metadata: dict[str, JsonValue]) -> tuple[bool, str, str]:
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
                evidence_metadata=artifact_metadata,
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
    parser.add_argument("--expected-package-prefix", type=Path, required=True)
    parser.add_argument("--artifact-kind", choices=("wheel", "sdist"), required=True)
    parser.add_argument("--artifact-input-sha256", required=True)
    parser.add_argument("--artifact-installed-sha256", required=True)
    parser.add_argument("--lock-sha256", required=True)
    parser.add_argument("--constraints-sha256", required=True)
    args = parser.parse_args()
    for value in (
        args.artifact_input_sha256,
        args.artifact_installed_sha256,
        args.lock_sha256,
        args.constraints_sha256,
    ):
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("Artifact certification digest must be lowercase SHA-256.")
    package_path = Path(fastapi_mergen.__file__).resolve()
    prefix = args.expected_package_prefix.resolve()
    if not package_path.is_relative_to(prefix):
        raise RuntimeError(
            f"Certification imported outside the artifact environment: {package_path}"
        )
    os.environ["MERGEN_EXPECTED_PACKAGE_PREFIX"] = str(prefix)
    artifact_metadata: dict[str, JsonValue] = {
        "artifact.kind": args.artifact_kind,
        "artifact.input_sha256": args.artifact_input_sha256,
        "artifact.installed_sha256": args.artifact_installed_sha256,
        "artifact.package_origin_verified": True,
        "artifact.lock_sha256": args.lock_sha256,
        "artifact.constraints_sha256": args.constraints_sha256,
    }
    certified, manifest_json, report_json = asyncio.run(_generate(artifact_metadata))
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(manifest_json, encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_json, encoding="utf-8")
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())

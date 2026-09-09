#!/usr/bin/env python3
"""Rehearse a disposable PostgreSQL server restart without exposing credentials."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncpg
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.postgres import provision_test_database

from fastapi_mergen import (
    AuthorizationMode,
    Event,
    MergenUnitOfWork,
    Principal,
    RetryPolicy,
)
from fastapi_mergen import __version__ as mergen_version
from fastapi_mergen.core.routing import RouteSpecification
from fastapi_mergen.postgres.diagnostics import inspect_runtime_database
from fastapi_mergen.postgres.revisions import check_schema_revisions
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.postgres.store import PostgresStore
from fastapi_mergen.sqlalchemy.models import DeliveryRow, EventRow

_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _route() -> RouteSpecification:
    return RouteSpecification(
        event_type="chaos.restart",
        route_key="chaos.restart",
        version=1,
        destination_kind="handler",
        destination_key="chaos.restart",
        required_scopes=(),
        authorization=AuthorizationMode.SNAPSHOT,
        service_policy=None,
        service_capabilities=None,
        maximum_snapshot_age_seconds=300,
        retry_policy=RetryPolicy(
            name="chaos.restart",
            handler_timeout_seconds=1,
            lease_duration_seconds=10,
        ),
    )


async def _server_identity(admin_dsn: str) -> tuple[str, datetime]:
    connection = await asyncpg.connect(admin_dsn, timeout=3)
    try:
        version = str(await connection.fetchval("SHOW server_version"))
        started_at = await connection.fetchval("SELECT pg_postmaster_start_time()")
        if not isinstance(started_at, datetime):
            raise RuntimeError("PostgreSQL returned an invalid server start time.")
        return version, started_at
    finally:
        await connection.close()


async def _wait_for_server(admin_dsn: str, *, timeout_seconds: float) -> tuple[str, datetime]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    last_error: BaseException | None = None
    while loop.time() < deadline:
        try:
            return await _server_identity(admin_dsn)
        except (TimeoutError, OSError, asyncpg.PostgresError) as exc:
            last_error = exc
            await asyncio.sleep(0.25)
    raise RuntimeError(
        "PostgreSQL did not recover within the bounded restart window."
    ) from last_error


async def _ensure_restart_persists_cluster(container: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "inspect",
        "--format",
        "{{json .Mounts}}",
        container,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Docker inspect failed: {detail or 'no diagnostic supplied'}")
    mounts = json.loads(stdout)
    if any(
        mount.get("Type") == "tmpfs"
        and str(mount.get("Destination", "")).startswith("/var/lib/postgresql")
        for mount in mounts
        if isinstance(mount, dict)
    ):
        raise RuntimeError(
            "Restart rehearsal requires persistent PostgreSQL storage; tmpfs would discard it."
        )


async def _restart_container(container: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "restart",
        "--time",
        "5",
        container,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Docker restart failed: {detail or 'no diagnostic supplied'}")


async def _rehearse(
    *,
    admin_dsn: str,
    container: str,
    expected_major: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    await _ensure_restart_persists_cluster(container)
    before_version, before_started_at = await _server_identity(admin_dsn)
    if before_version.split(".", maxsplit=1)[0] != str(expected_major):
        raise RuntimeError(
            f"Expected PostgreSQL {expected_major}, connected to {before_version!r}."
        )

    async with provision_test_database(admin_dsn) as database:
        roles = RuntimeRoles(
            migration=database.migration_role,
            application=database.app_role,
            relay=database.relay_role,
        )
        migration = create_async_engine(database.migration_sqlalchemy_dsn)
        application = create_async_engine(database.app_sqlalchemy_dsn, pool_pre_ping=True)
        sessions = async_sessionmaker(application, expire_on_commit=False)
        principal = Principal(tenant_id=uuid4(), subject_id="chaos:restart")
        try:
            await install_core_schema(migration, roles=roles)
            async with sessions() as session:
                uow = MergenUnitOfWork(
                    session=session,
                    principal=principal,
                    store=PostgresStore(),
                    routes=(_route(),),
                )
                async with uow:
                    committed = await uow.emit(
                        Event(type="chaos.restart", version=1, data={"probe": "committed"})
                    )
            async with application.connect() as connection:
                before_backend_pid = int(await connection.scalar(text("SELECT pg_backend_pid()")))

            await _restart_container(container)
            after_version, after_started_at = await _wait_for_server(
                admin_dsn,
                timeout_seconds=timeout_seconds,
            )
            if after_started_at <= before_started_at:
                raise RuntimeError("The target PostgreSQL server did not report a new start time.")

            await check_schema_revisions(application, components=("core",))
            doctor = await inspect_runtime_database(
                application,
                expected_role=database.app_role,
                roles=roles,
            )
            if not doctor.healthy:
                failed_codes = [
                    check.code for check in doctor.checks if check.status.value == "fail"
                ]
                raise RuntimeError("Post-restart doctor failed: " + ", ".join(failed_codes))

            async with sessions() as session, session.begin():
                after_backend_pid = int(await session.scalar(text("SELECT pg_backend_pid()")))
                await session.execute(
                    text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                    {"tenant": str(principal.tenant_id)},
                )
                event_ids = tuple((await session.scalars(select(EventRow.event_id))).all())
                delivery_count = int(
                    await session.scalar(select(func.count()).select_from(DeliveryRow)) or 0
                )
            if event_ids != (committed.event_id,) or delivery_count != 1:
                raise RuntimeError("Committed event or delivery identity was not preserved.")

            return {
                "schema_version": 1,
                "captured_on": datetime.now(UTC).date().isoformat(),
                "platform": platform.system().lower() + "-" + platform.machine().lower(),
                "fastapi_mergen": mergen_version,
                "postgresql_before": before_version,
                "postgresql_after": after_version,
                "expected_major": expected_major,
                "result": "pass",
                "restart_observed": True,
                "backend_replaced": before_backend_pid != after_backend_pid,
                "schema_compatible": True,
                "doctor_healthy": True,
                "event_identity_preserved": True,
                "delivery_identity_preserved": True,
            }
        finally:
            await application.dispose()
            await migration.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--expected-major", type=int, choices=(16, 18), required=True)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--admin-dsn", default=os.getenv("MERGEN_TEST_ADMIN_DSN"))
    args = parser.parse_args()
    if not args.admin_dsn:
        parser.error("set MERGEN_TEST_ADMIN_DSN or pass --admin-dsn")
    if not _CONTAINER.fullmatch(args.container):
        parser.error("container name contains unsupported characters")
    if args.timeout_seconds <= 0 or args.timeout_seconds > 300:
        parser.error("timeout must be greater than zero and no more than 300 seconds")

    report = asyncio.run(
        _rehearse(
            admin_dsn=args.admin_dsn,
            container=args.container,
            expected_major=args.expected_major,
            timeout_seconds=args.timeout_seconds,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

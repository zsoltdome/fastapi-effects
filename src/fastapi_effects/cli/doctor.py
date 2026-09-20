"""CLI adapter for live PostgreSQL diagnostics."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from fastapi_effects.postgres.diagnostics import inspect_runtime_database


def run_doctor(
    dsn: str,
    *,
    expected_role: str | None = None,
    application_table: str | None = None,
) -> int:
    return asyncio.run(
        _run_doctor(
            dsn,
            expected_role=expected_role,
            application_table=application_table,
        )
    )


async def _run_doctor(
    dsn: str,
    *,
    expected_role: str | None,
    application_table: str | None,
) -> int:
    engine = create_async_engine(_asyncpg_dsn(dsn), pool_pre_ping=True)
    try:
        report = await inspect_runtime_database(
            engine,
            expected_role=expected_role,
            application_table=application_table,
        )
    except Exception:
        print("FAIL database.connection: diagnostic connection or query failed")
        return 2
    finally:
        await engine.dispose()
    for check in report.checks:
        print(f"{check.status.value.upper()} {check.code}: {check.summary}")
    return 0 if report.healthy else 2


def _asyncpg_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgresql://"):
        return "postgresql+asyncpg://" + dsn.removeprefix("postgresql://")
    raise ValueError("Doctor requires a PostgreSQL DSN.")


__all__ = ["run_doctor"]

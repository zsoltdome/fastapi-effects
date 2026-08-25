"""Attributable environment metadata for real-runtime certification adapters."""

from __future__ import annotations

import os
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_mergen import __version__
from fastapi_mergen.conformance.safety import JsonValue
from fastapi_mergen.postgres.revisions import read_schema_revisions


async def postgres_evidence_metadata(engine: AsyncEngine) -> dict[str, JsonValue]:
    """Bind certification evidence to exact code, schema, database, and driver versions."""

    async with engine.connect() as connection:
        database_version = str(await connection.scalar(text("SHOW server_version")))
    revisions = await read_schema_revisions(engine)
    return {
        "package.version": __version__,
        "implementation.commit": _implementation_commit(),
        "database.product": "PostgreSQL",
        "database.version": database_version,
        "database.driver": "asyncpg",
        "database.driver_version": _distribution_version("asyncpg"),
        "schema.revisions": dict(revisions),
    }


def _distribution_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unavailable"


def _implementation_commit() -> str:
    configured = os.getenv("MERGEN_IMPLEMENTATION_COMMIT") or os.getenv("GITHUB_SHA")
    if configured:
        return configured[:64]
    for parent in Path(__file__).resolve().parents:
        if not (parent / ".git").exists():
            continue
        completed = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=parent,
            check=False,
            capture_output=True,
            text=True,
        )
        commit = completed.stdout.strip()
        if completed.returncode == 0 and commit:
            return commit[:64]
        break
    return "unavailable"


__all__ = ["postgres_evidence_metadata"]

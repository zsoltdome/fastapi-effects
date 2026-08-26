#!/usr/bin/env python3
"""Write one execution-bound compatibility result for workflow artifacts."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRACKED_DISTRIBUTIONS = (
    "fastapi-mergen",
    "alembic",
    "asyncpg",
    "cryptography",
    "fastapi",
    "fastmcp",
    "httpx",
    "opentelemetry-api",
    "opentelemetry-sdk",
    "pydantic",
    "sqlalchemy",
    "standardwebhooks",
    "starlette",
    "taskiq",
    "taskiq-redis",
)


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _commit() -> str:
    configured = os.getenv("MERGEN_IMPLEMENTATION_COMMIT") or os.getenv("GITHUB_SHA")
    if configured:
        return configured
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


async def _database_binding() -> dict[str, str] | None:
    dsn = os.getenv("MERGEN_TEST_ADMIN_DSN")
    if not dsn:
        return None
    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        version = await connection.fetchval("SHOW server_version")
    finally:
        await connection.close()
    return {
        "product": "PostgreSQL",
        "version": str(version),
        "driver": "asyncpg",
        "driver_version": _version("asyncpg") or "unavailable",
    }


async def _payload(evidence_id: str, selection: str) -> dict[str, Any]:
    lock_bytes = (ROOT / "uv.lock").read_bytes()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "evidence_id": evidence_id,
        "result": "pass",
        "release_authority": True,
        "binding": {
            "package_version": _version("fastapi-mergen"),
            "implementation_commit": _commit(),
            "lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "workflow_run_id": os.getenv("GITHUB_RUN_ID", "local"),
            "workflow_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "local"),
        },
        "selection": selection,
        "distributions": {
            name: version
            for name in TRACKED_DISTRIBUTIONS
            if (version := _version(name)) is not None
        },
    }
    database = await _database_binding()
    if database is not None:
        payload["database"] = database
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection", required=True)
    args = parser.parse_args()
    payload = asyncio.run(_payload(args.evidence_id, args.selection))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

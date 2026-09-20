#!/usr/bin/env python3
"""Compare source and restored FastAPIEffects databases without emitting protected values."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TABLES = (
    "schema_revision",
    "events",
    "deliveries",
    "attempts",
    "webhook_secret_sets",
    "webhook_subscriptions",
    "webhook_secret_versions",
    "webhook_subscription_versions",
    "webhook_audit",
    "taskiq_handoffs",
    "commands",
)


@dataclass(frozen=True, slots=True)
class TableIdentity:
    rows: int
    digest: str


def _async_dsn(dsn: str) -> str:
    parsed = urlsplit(dsn)
    if parsed.scheme in {"postgres", "postgresql"}:
        return urlunsplit(("postgresql+asyncpg", parsed.netloc, parsed.path, parsed.query, ""))
    if parsed.scheme == "postgresql+asyncpg":
        return dsn
    raise ValueError("restore DSN must use PostgreSQL with asyncpg")


def _protected_json(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _protected_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_protected_json(item) for item in value]
    return value


async def database_identity(engine: AsyncEngine) -> dict[str, TableIdentity]:
    result: dict[str, TableIdentity] = {}
    async with engine.connect() as connection:
        for table in TABLES:
            rows = (await connection.execute(text(f"SELECT * FROM fastapi_effects.{table}"))).all()
            row_digests = []
            for row in rows:
                protected = _protected_json(dict(row._mapping))
                encoded = json.dumps(
                    protected,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode()
                row_digests.append(hashlib.sha256(encoded).hexdigest())
            aggregate = hashlib.sha256("\n".join(sorted(row_digests)).encode()).hexdigest()
            result[table] = TableIdentity(rows=len(rows), digest=aggregate)
    return result


async def compare_restore(source_dsn: str, restored_dsn: str) -> dict[str, TableIdentity]:
    if source_dsn == restored_dsn:
        raise ValueError("source and restored DSNs must identify separate databases")
    source = create_async_engine(_async_dsn(source_dsn))
    restored = create_async_engine(_async_dsn(restored_dsn))
    try:
        source_identity, restored_identity = await asyncio.gather(
            database_identity(source),
            database_identity(restored),
        )
    finally:
        await restored.dispose()
        await source.dispose()
    mismatches = [table for table in TABLES if source_identity[table] != restored_identity[table]]
    if mismatches:
        raise RuntimeError("Restore identity mismatch in: " + ", ".join(mismatches))
    return source_identity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dsn", required=True)
    parser.add_argument("--restored-dsn", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    identities = asyncio.run(compare_restore(args.source_dsn, args.restored_dsn))
    report = {
        "schema_version": 1,
        "result": "pass",
        "tables": {
            table: {"rows": value.rows, "digest": value.digest}
            for table, value in identities.items()
        },
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

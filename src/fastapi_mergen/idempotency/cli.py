"""Command-ledger maintenance CLI."""

from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_mergen.cli.doctor import _asyncpg_dsn
from fastapi_mergen.idempotency.operations import prune_commands


def run_prune(dsn: str, *, before: str, batch_size: int) -> int:
    try:
        cutoff = datetime.fromisoformat(before.replace("Z", "+00:00"))
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError
    except ValueError:
        print("commands prune requires an ISO-8601 timezone-aware --before value")
        return 2
    return asyncio.run(_run_prune(dsn, before=cutoff, batch_size=batch_size))


async def _run_prune(dsn: str, *, before: datetime, batch_size: int) -> int:
    engine = create_async_engine(_asyncpg_dsn(dsn), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            deleted = await prune_commands(session, before=before, batch_size=batch_size)
    except Exception:
        print("commands prune failed without modifying an uncommitted batch")
        return 2
    finally:
        await engine.dispose()
    print(f"commands pruned: {deleted}")
    return 0


__all__ = ["run_prune"]

"""Restricted command-ledger maintenance operations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.idempotency.store import CommandStore


async def prune_commands(
    session: AsyncSession,
    *,
    before: datetime,
    batch_size: int = 100,
) -> int:
    return await CommandStore().prune(session, before=before, batch_size=batch_size)


__all__ = ["prune_commands"]

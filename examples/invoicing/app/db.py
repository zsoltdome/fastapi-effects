"""Lazy async-session dependency for the reference application."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Create a disposable session only when an HTTP operation is invoked.

    The lazy design lets documentation and OpenAPI generation boot without requiring
    the PostgreSQL driver or a live database. It is intentionally simple for M1.
    """
    url = os.getenv("MERGEN_EXAMPLE_DATABASE_URL")
    if not url:
        raise RuntimeError("MERGEN_EXAMPLE_DATABASE_URL is required for database operations.")
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()

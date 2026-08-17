"""Lazy async-session dependency for the reference application."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_mergen import Principal


def _database_url() -> str:
    url = os.getenv("MERGEN_EXAMPLE_DATABASE_URL")
    if not url:
        raise RuntimeError("MERGEN_EXAMPLE_DATABASE_URL is required for database operations.")
    return url


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Create a disposable session only when an HTTP operation is invoked.

    The lazy design lets documentation and OpenAPI generation boot without requiring
    the PostgreSQL driver or a live database. It is intentionally simple for M1.
    """
    engine = create_async_engine(_database_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


@asynccontextmanager
async def get_handler_session(principal: Principal) -> AsyncIterator[AsyncSession]:
    """Open a new application-role transaction bound to the delivery tenant."""
    engine = create_async_engine(_database_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await session.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(principal.tenant_id)},
            )
            await session.execute(
                text("SELECT set_config('mergen.subject_id', :subject_id, true)"),
                {"subject_id": principal.subject_id},
            )
            yield session
    finally:
        await engine.dispose()

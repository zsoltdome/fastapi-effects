"""Process-lifetime application pool for the reference application."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_mergen import Principal


def _database_url() -> str:
    url = os.getenv("MERGEN_EXAMPLE_DATABASE_URL")
    if not url:
        raise RuntimeError("MERGEN_EXAMPLE_DATABASE_URL is required for database operations.")
    return url


_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def start_database() -> None:
    """Create one application-role pool for this app or relay process."""

    global _engine, _sessions
    if _engine is not None:
        return
    _engine = create_async_engine(_database_url(), pool_pre_ping=True)
    _sessions = async_sessionmaker(_engine, expire_on_commit=False)


async def stop_database() -> None:
    """Dispose the process pool during application or relay shutdown."""

    global _engine, _sessions
    engine = _engine
    _engine = None
    _sessions = None
    if engine is not None:
        await engine.dispose()


def _session_factory() -> async_sessionmaker[AsyncSession]:
    if _sessions is None:
        raise RuntimeError("The invoicing database pool has not been started.")
    return _sessions


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Open one request session from the process-lifetime app-role pool."""

    async with _session_factory()() as session:
        yield session


@asynccontextmanager
async def get_handler_session(principal: Principal) -> AsyncIterator[AsyncSession]:
    """Open a new application-role transaction bound to the delivery tenant."""

    async with _session_factory()() as session, session.begin():
        await session.execute(
            text("SELECT set_config('mergen.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(principal.tenant_id)},
        )
        await session.execute(
            text("SELECT set_config('mergen.subject_id', :subject_id, true)"),
            {"subject_id": principal.subject_id},
        )
        yield session

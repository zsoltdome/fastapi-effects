"""Fresh tenant-bound application-session provider helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_mergen.core.principal import Principal


def tenant_session_provider(
    sessions: async_sessionmaker[AsyncSession],
) -> Callable[[Principal], AbstractAsyncContextManager[AsyncSession]]:
    """Build a provider that never reuses the relay or request session."""

    @asynccontextmanager
    async def provide(principal: Principal) -> AsyncIterator[AsyncSession]:
        async with sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(principal.tenant_id)},
            )
            await session.execute(
                text("SELECT set_config('mergen.subject_id', :subject_id, true)"),
                {"subject_id": principal.subject_id},
            )
            yield session

    return provide


__all__ = ["tenant_session_provider"]

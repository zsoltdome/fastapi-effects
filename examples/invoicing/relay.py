"""Installed-package relay factory with separate relay/app credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from fastapi_effects.postgres import PollingRelay, RelayConfig

from .app.db import start_database, stop_database
from .app.fastapi_effects_config import fastapi_effects


def _relay_database_url() -> str:
    value = os.getenv("FASTAPI_EFFECTS_EXAMPLE_RELAY_DATABASE_URL")
    if not value:
        raise RuntimeError("FASTAPI_EFFECTS_EXAMPLE_RELAY_DATABASE_URL is required by the relay.")
    return value


@dataclass(slots=True)
class InvoicingRelay(PollingRelay):
    relay_engine: AsyncEngine | None = None

    async def run(self) -> None:
        try:
            await super().run()
        finally:
            if self.relay_engine is not None:
                await self.relay_engine.dispose()
            await stop_database()


def create_relay() -> PollingRelay:
    """Create app/relay process pools; the CLI disposes them after bounded stop."""

    start_database()
    engine = create_async_engine(_relay_database_url(), pool_pre_ping=True)
    return InvoicingRelay(
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        sink=fastapi_effects.handler_executor(),
        config=RelayConfig(),
        relay_engine=engine,
    )

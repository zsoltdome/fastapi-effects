"""FastAPI invoicing application for the M8 runtime vertical slice."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi_effects import __version__

from .api import router
from .db import start_database, stop_database
from .fastapi_effects_config import fastapi_effects


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    start_database()
    try:
        fastapi_effects.freeze()
        yield
    finally:
        await stop_database()


app = FastAPI(
    title="FastAPI Effects Invoicing Example",
    version=__version__,
    lifespan=lifespan,
)
app.include_router(router)

"""FastAPI invoicing application for the M8 runtime vertical slice."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi_mergen import __version__

from .api import router
from .mergen_config import mergen


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    mergen.freeze()
    yield


app = FastAPI(
    title="FastAPI-Mergen Invoicing Example",
    version=__version__,
    lifespan=lifespan,
)
app.include_router(router)

"""Bootable FastAPI application for OpenAPI and dependency-shape validation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import router
from .mergen_config import mergen


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    mergen.freeze()
    yield


app = FastAPI(
    title="FastAPI-Mergen Invoicing Example",
    version="0.0.1",
    lifespan=lifespan,
)
app.include_router(router)

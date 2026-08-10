"""Explicit FastAPI-facing command helpers and bounded error mapping."""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from fastapi_mergen.core.principal import Principal
from fastapi_mergen.errors import (
    AuthenticationRequired,
    AuthorizationDenied,
    CommandConflict,
    CommandInProgress,
    MergenConfigurationError,
)
from fastapi_mergen.idempotency.command import CommandContext
from fastapi_mergen.idempotency.fingerprint import BodyFingerprintMode
from fastapi_mergen.idempotency.request import PreparedCommand, prepare_request


async def prepare_command(
    request: Request,
    *,
    principal: Principal,
    route_id: str,
    body_mode: BodyFingerprintMode = BodyFingerprintMode.CANONICAL_JSON,
    representation_headers: tuple[str, ...] = (
        "content-encoding",
        "if-match",
        "if-none-match",
    ),
) -> PreparedCommand:
    return await prepare_request(
        request,
        principal=principal,
        route_id=route_id,
        body_mode=body_mode,
        representation_headers=representation_headers,
    )


def command_context(
    session: AsyncSession,
    *,
    principal: Principal,
    prepared: PreparedCommand,
    ttl: timedelta = timedelta(hours=24),
) -> CommandContext:
    return CommandContext(
        session=session,
        principal=principal,
        identity=prepared.identity,
        fingerprint=prepared.fingerprint,
        ttl=ttl,
    )


def command_http_exception(error: Exception) -> HTTPException:
    """Map public command failures without returning stored identity material."""
    if isinstance(error, AuthenticationRequired):
        return HTTPException(status_code=401, detail="Authentication is required.")
    if isinstance(error, AuthorizationDenied):
        return HTTPException(status_code=403, detail="Command authority was denied.")
    if isinstance(error, (CommandConflict, CommandInProgress)):
        return HTTPException(status_code=409, detail="Idempotency identity conflicts.")
    if isinstance(error, MergenConfigurationError):
        lowered = str(error).lower()
        if "oversized" in lowered or "limit" in lowered:
            return HTTPException(status_code=413, detail="Command representation is too large.")
        return HTTPException(status_code=422, detail="Command representation is invalid.")
    return HTTPException(status_code=500, detail="Command transaction failed.")


__all__ = ["command_context", "command_http_exception", "prepare_command"]

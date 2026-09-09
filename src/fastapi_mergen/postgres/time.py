"""Authoritative wall-clock sampling for lock-sensitive PostgreSQL operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.errors import MergenConfigurationError


class DatabaseClock(Protocol):
    """Clock used at PostgreSQL lock and persistence boundaries."""

    async def now(self, session: AsyncSession, *, observed_at: datetime) -> datetime: ...


@dataclass(frozen=True, slots=True)
class PostgresDatabaseClock:
    """Use the database wall clock regardless of application-clock skew."""

    async def now(self, session: AsyncSession, *, observed_at: datetime) -> datetime:
        return await database_now(session, observed_at=observed_at)


async def database_now(session: AsyncSession, *, observed_at: datetime) -> datetime:
    """Sample actual PostgreSQL time after validating the caller observation.

    ``clock_timestamp()`` advances during a transaction, unlike ``now()``. The
    caller timestamp remains a policy input, but it cannot backdate, advance, or
    extend a production persistence boundary.
    """

    value = await session.scalar(select(func.clock_timestamp()))
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise MergenConfigurationError("PostgreSQL returned an invalid authoritative timestamp.")
    return value


__all__ = ["DatabaseClock", "PostgresDatabaseClock", "database_now"]

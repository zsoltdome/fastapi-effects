"""Read-only PostgreSQL operational observations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_effects.observability.events import RuntimeEvent, RuntimeEventKind
from fastapi_effects.observability.protocols import EventSink, record_safely


async def observe_backlog(engine: AsyncEngine, sink: EventSink) -> float:
    """Record oldest claimable backlog age without tenant-cardinality labels."""

    async with engine.connect() as connection:
        age = await connection.scalar(
            text(
                "SELECT COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - min(created_at))), 0) "
                "FROM fastapi_effects.deliveries "
                "WHERE state IN ('pending', 'retry_wait')"
            )
        )
    seconds = max(0.0, float(age or 0.0))
    record_safely(
        sink,
        RuntimeEvent(
            RuntimeEventKind.BACKLOG_OBSERVED,
            datetime.now(UTC),
            {"backlog.age.seconds": seconds},
        ),
    )
    return seconds


__all__ = ["observe_backlog"]

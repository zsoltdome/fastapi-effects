"""PostgreSQL-backed atomic event and fanout store."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fastapi_mergen.core.event import Event, EventRecord
from fastapi_mergen.core.identity import DedupeIdentity
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.protocols import Clock, UUIDGenerator
from fastapi_mergen.core.routing import RouteSpecification
from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_mergen.observability.protocols import EventSink, NoOpEventSink, record_safely
from fastapi_mergen.sqlalchemy.repository import RuntimeRepository

_SCHEMA_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


@dataclass(frozen=True, slots=True)
class PostgresStore:
    """Store immutable event intent and original delivery snapshots atomically."""

    schema: str = "fastapi_mergen"
    event_sink: EventSink = field(default_factory=NoOpEventSink, repr=False, compare=False)
    _repository: RuntimeRepository = field(
        default_factory=RuntimeRepository,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.schema, str) or not _SCHEMA_NAME_PATTERN.fullmatch(self.schema):
            raise MergenConfigurationError("PostgreSQL schema name is invalid.")
        if self.schema != "fastapi_mergen":
            raise MergenConfigurationError(
                "The supported PostgreSQL schema is exactly 'fastapi_mergen'."
            )

    @property
    def name(self) -> str:
        """Return the stable store identifier used by diagnostics."""

        return "postgresql"

    async def check_schema(self, engine: AsyncEngine) -> None:
        """Fail startup on any incompatible v1 component without migrating it."""

        from fastapi_mergen.postgres.revisions import check_schema_revisions

        await check_schema_revisions(engine)

    async def publish(
        self,
        *,
        session: AsyncSession,
        principal: Principal,
        event: Event[object],
        routes: Sequence[RouteSpecification],
        clock: Clock,
        uuid_source: UUIDGenerator,
        dedupe_namespace: str | None,
        dedupe_key: str | None,
    ) -> EventRecord:
        """Insert one event and every original route inside the active transaction."""
        if (dedupe_namespace is None) != (dedupe_key is None):
            raise MergenConfigurationError("Dedupe namespace and key must be paired.")
        identity = (
            None
            if dedupe_namespace is None or dedupe_key is None
            else DedupeIdentity(namespace=dedupe_namespace, key=dedupe_key)
        )
        now = clock.now()
        record = await self._repository.publish(
            session=session,
            principal=principal,
            event=event,
            routes=routes,
            now=now,
            uuid_source=uuid_source,
            dedupe_identity=identity,
        )
        record_safely(
            self.event_sink,
            RuntimeEvent(
                kind=RuntimeEventKind.PUBLISHED,
                occurred_at=now,
                attributes={"destination.count": len(routes)},
                lineage=TraceLineage(event_id=record.event_id, traceparent=record.traceparent),
            ),
        )
        return record

"""Typed event value used by the Milestone 1 API spike."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, TypeVar
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError

PayloadT = TypeVar("PayloadT", covariant=True)
_EVENT_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class Event(Generic[PayloadT]):
    """Immutable typed intent supplied to an active Mergen unit of work."""

    type: str
    version: int
    data: PayloadT
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    traceparent: str | None = None
    tracestate: str | None = None

    def __post_init__(self) -> None:
        if not _EVENT_TYPE_PATTERN.fullmatch(self.type):
            raise MergenConfigurationError(
                "Event type must use lower-case letters, digits, dots, underscores, or hyphens."
            )
        if self.version < 1:
            raise MergenConfigurationError("Event version must be positive.")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise MergenConfigurationError("Event occurred_at must be timezone-aware.")
        if self.traceparent is not None and len(self.traceparent) > 256:
            raise MergenConfigurationError("Event traceparent is too long.")
        if self.tracestate is not None and len(self.tracestate) > 512:
            raise MergenConfigurationError("Event tracestate is too long.")

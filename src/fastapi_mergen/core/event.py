"""Typed event value used by the Milestone 1 API spike."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, TypeVar
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError

PayloadT = TypeVar("PayloadT", covariant=True)


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
        if not self.type.strip():
            raise MergenConfigurationError("Event type must not be blank.")
        if self.version < 1:
            raise MergenConfigurationError("Event version must be positive.")

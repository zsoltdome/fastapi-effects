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
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


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
        if not isinstance(self.type, str) or not _EVENT_TYPE_PATTERN.fullmatch(self.type):
            raise MergenConfigurationError(
                "Event type must use lower-case letters, digits, dots, underscores, or hyphens."
            )
        if not _is_positive_integer(self.version):
            raise MergenConfigurationError("Event version must be a positive integer.")
        if not isinstance(self.occurred_at, datetime):
            raise MergenConfigurationError("Event occurred_at must be a datetime.")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise MergenConfigurationError("Event occurred_at must be timezone-aware.")
        _validate_optional_uuid("correlation_id", self.correlation_id)
        _validate_optional_uuid("causation_id", self.causation_id)
        _validate_trace_field("traceparent", self.traceparent, maximum_length=256)
        _validate_trace_field("tracestate", self.tracestate, maximum_length=512)


def _is_positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_optional_uuid(name: str, value: object) -> None:
    if value is not None and not isinstance(value, UUID):
        raise MergenConfigurationError(f"Event {name} must be a UUID when provided.")


def _validate_trace_field(name: str, value: object, *, maximum_length: int) -> None:
    if value is None:
        return
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum_length
        or _CONTROL_CHARACTER_PATTERN.search(value) is not None
    ):
        raise MergenConfigurationError(f"Event {name} is invalid.")

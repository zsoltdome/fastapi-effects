"""Bounded, low-cardinality runtime event vocabulary."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError

_ATTRIBUTE = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_FORBIDDEN = re.compile(
    r"(^|[._])(payload|body|authorization|cookie|credential|password|secret|token|api_key)([._]|$)",
    re.IGNORECASE,
)
_ALLOWED_ATTRIBUTES = frozenset(
    {
        "attempt.number",
        "authorization.result",
        "auto_paused",
        "backlog.age.seconds",
        "capability",
        "destination.count",
        "destination.kind",
        "duration",
        "duration.ms",
        "executed",
        "failure.code",
        "outcome",
        "pruned.count",
        "reconciled.count",
        "state",
    }
)


class RuntimeEventKind(StrEnum):
    PUBLISHED = "published"
    CLAIMED = "claimed"
    ATTEMPTED = "attempted"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    DEAD = "dead"
    LEASE_LOST = "lease_lost"
    RECONCILED = "reconciled"
    REPLAYED = "replayed"
    WEBHOOK_ATTEMPTED = "webhook_attempted"
    WEBHOOK_PAUSED = "webhook_paused"
    WEBHOOK_PRUNED = "webhook_pruned"
    WEBHOOK_SECRET_CHANGED = "webhook_secret_changed"
    TASKIQ_PREPARED = "taskiq_prepared"
    TASKIQ_ENQUEUED = "taskiq_enqueued"
    TASKIQ_EXECUTED = "taskiq_executed"
    COMMAND_STARTED = "command_started"
    COMMAND_COMPLETED = "command_completed"
    COMMAND_REPLAYED = "command_replayed"
    COMMAND_CONFLICT = "command_conflict"
    COMMAND_PRUNED = "command_pruned"
    DELEGATION_ISSUED = "delegation_issued"
    DELEGATION_ALLOWED = "delegation_allowed"
    DELEGATION_DENIED = "delegation_denied"
    BACKLOG_OBSERVED = "backlog_observed"


@dataclass(frozen=True, slots=True)
class TraceLineage:
    """High-cardinality identifiers reserved for traces, never metric labels."""

    event_id: UUID | None = None
    delivery_id: UUID | None = None
    attempt_id: UUID | None = None
    replay_of: UUID | None = None
    handoff_id: UUID | None = None
    command_id: UUID | None = None
    delegation_id: UUID | None = None
    traceparent: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.event_id,
            self.delivery_id,
            self.attempt_id,
            self.replay_of,
            self.handoff_id,
            self.command_id,
            self.delegation_id,
        ):
            if value is not None and not isinstance(value, UUID):
                raise MergenConfigurationError("Runtime trace lineage identity is invalid.")
        if self.traceparent is not None and (
            not isinstance(self.traceparent, str)
            or len(self.traceparent) > 256
            or _CONTROL_CHARACTER_PATTERN.search(self.traceparent) is not None
        ):
            raise MergenConfigurationError("Runtime trace lineage parent is invalid.")

    def attributes(self) -> Mapping[str, str]:
        values = {
            "event.id": self.event_id,
            "delivery.id": self.delivery_id,
            "attempt.id": self.attempt_id,
            "replay.of": self.replay_of,
            "handoff.id": self.handoff_id,
            "command.id": self.command_id,
            "delegation.id": self.delegation_id,
        }
        result = {name: str(value) for name, value in values.items() if value is not None}
        if self.traceparent is not None:
            result["trace.parent"] = self.traceparent
        return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    kind: RuntimeEventKind
    occurred_at: datetime
    attributes: Mapping[str, str | int | float | bool]
    lineage: TraceLineage = TraceLineage()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RuntimeEventKind):
            raise MergenConfigurationError("Runtime event kind is invalid.")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise MergenConfigurationError("Runtime event time must be timezone-aware.")
        if len(self.attributes) > 32:
            raise MergenConfigurationError("Runtime event has too many attributes.")
        normalized: dict[str, str | int | float | bool] = {}
        for key, value in self.attributes.items():
            if (
                not isinstance(key, str)
                or not _ATTRIBUTE.fullmatch(key)
                or _FORBIDDEN.search(key)
                or key not in _ALLOWED_ATTRIBUTES
            ):
                raise MergenConfigurationError("Runtime event contains an unsafe attribute.")
            if not isinstance(value, (str, int, float, bool)):
                raise MergenConfigurationError("Runtime event attribute type is unsupported.")
            if isinstance(value, float) and not math.isfinite(value):
                raise MergenConfigurationError("Runtime event attribute must be finite.")
            if isinstance(value, str) and len(value) > 256:
                raise MergenConfigurationError("Runtime event attribute is oversized.")
            normalized[key] = value
        object.__setattr__(self, "attributes", MappingProxyType(normalized))
        if not isinstance(self.lineage, TraceLineage):
            raise MergenConfigurationError("Runtime event trace lineage is invalid.")


__all__ = ["RuntimeEvent", "RuntimeEventKind", "TraceLineage"]

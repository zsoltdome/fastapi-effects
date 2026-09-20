"""Typed event intent and detached immutable persistence records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import UUID

from fastapi_effects.core.identity import DedupeIdentity
from fastapi_effects.core.principal import PrincipalEnvelope
from fastapi_effects.errors import FastAPIEffectsConfigurationError

PayloadT = TypeVar("PayloadT", covariant=True)
_EVENT_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_TRACEPARENT = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace>[0-9a-f]{32})-"
    r"(?P<parent>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$"
)
_TRACESTATE_KEY = re.compile(r"^[a-z0-9][a-z0-9_*/-]{0,255}(?:@[a-z0-9][a-z0-9_*/-]{0,13})?$")


@dataclass(frozen=True, slots=True)
class Event(Generic[PayloadT]):
    """Immutable typed intent supplied to an active FastAPIEffects unit of work."""

    type: str
    version: int
    data: PayloadT
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    traceparent: str | None = None
    tracestate: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not _EVENT_TYPE_PATTERN.fullmatch(self.type):
            raise FastAPIEffectsConfigurationError(
                "Event type must use lower-case letters, digits, dots, underscores, or hyphens."
            )
        if not _is_positive_integer(self.version):
            raise FastAPIEffectsConfigurationError("Event version must be a positive integer.")
        if not isinstance(self.occurred_at, datetime):
            raise FastAPIEffectsConfigurationError("Event occurred_at must be a datetime.")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise FastAPIEffectsConfigurationError("Event occurred_at must be timezone-aware.")
        _validate_optional_uuid("correlation_id", self.correlation_id)
        _validate_optional_uuid("causation_id", self.causation_id)
        _validate_traceparent(self.traceparent)
        _validate_tracestate(self.tracestate)


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Detached durable origin facts; payload bytes are format-tagged canonical JSON."""

    event_id: UUID
    tenant_id: UUID
    event_type: str
    event_version: int
    canonical_version: int
    payload_canonical: bytes
    payload_sha256: bytes
    principal: PrincipalEnvelope
    occurred_at: datetime
    created_at: datetime
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    traceparent: str | None = None
    tracestate: str | None = None
    dedupe_namespace: str | None = None
    dedupe_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, UUID) or not isinstance(self.tenant_id, UUID):
            raise FastAPIEffectsConfigurationError("Event record identities must be UUID values.")
        Event(
            type=self.event_type,
            version=self.event_version,
            data=None,
            occurred_at=self.occurred_at,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
            traceparent=self.traceparent,
            tracestate=self.tracestate,
        )
        if not _is_positive_integer(self.canonical_version):
            raise FastAPIEffectsConfigurationError("Event canonical version must be positive.")
        if not isinstance(self.payload_canonical, bytes) or not self.payload_canonical:
            raise FastAPIEffectsConfigurationError(
                "Event canonical payload must be non-empty bytes."
            )
        if not isinstance(self.payload_sha256, bytes) or len(self.payload_sha256) != 32:
            raise FastAPIEffectsConfigurationError("Event payload digest must be SHA-256 bytes.")
        if not isinstance(self.principal, PrincipalEnvelope):
            raise FastAPIEffectsConfigurationError("Event record principal is invalid.")
        if self.principal.tenant_id != self.tenant_id:
            raise FastAPIEffectsConfigurationError("Event tenant and principal tenant must match.")
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
        ):
            raise FastAPIEffectsConfigurationError("Event created_at must be timezone-aware.")
        if (self.dedupe_namespace is None) != (self.dedupe_key is None):
            raise FastAPIEffectsConfigurationError("Event dedupe fields must be provided together.")
        if self.dedupe_namespace is not None and self.dedupe_key is not None:
            DedupeIdentity(namespace=self.dedupe_namespace, key=self.dedupe_key)


def _is_positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_optional_uuid(name: str, value: object) -> None:
    if value is not None and not isinstance(value, UUID):
        raise FastAPIEffectsConfigurationError(f"Event {name} must be a UUID when provided.")


def _validate_traceparent(value: object) -> None:
    if value is None:
        return
    match = _TRACEPARENT.fullmatch(value) if isinstance(value, str) else None
    if (
        match is None
        or match["version"] == "ff"
        or set(match["trace"]) == {"0"}
        or set(match["parent"]) == {"0"}
    ):
        raise FastAPIEffectsConfigurationError("Event traceparent is invalid.")


def _validate_tracestate(value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or _CONTROL_CHARACTER_PATTERN.search(value) is not None
    ):
        raise FastAPIEffectsConfigurationError("Event tracestate is invalid.")
    members = value.split(",")
    if len(members) > 32:
        raise FastAPIEffectsConfigurationError("Event tracestate is invalid.")
    seen: set[str] = set()
    for member in members:
        key, separator, member_value = member.partition("=")
        if (
            not separator
            or not _TRACESTATE_KEY.fullmatch(key)
            or key in seen
            or not member_value
            or member_value != member_value.strip()
            or "," in member_value
            or any(not 0x20 <= ord(character) <= 0x7E for character in member_value)
        ):
            raise FastAPIEffectsConfigurationError("Event tracestate is invalid.")
        seen.add(key)


__all__ = ["Event", "EventRecord"]

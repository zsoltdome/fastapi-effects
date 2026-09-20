"""Immutable delivery and append-only attempt domain records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from fastapi_effects.errors import FastAPIEffectsConfigurationError

_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class DeliveryState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    DEAD = "dead"


class AttemptOutcome(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    RETRYABLE = "retryable"
    TERMINAL = "terminal"
    ABANDONED = "abandoned"
    LEASE_LOST = "lease_lost"


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    delivery_id: UUID
    tenant_id: UUID
    event_id: UUID
    route_key: str
    route_version: int
    destination_kind: str
    destination_key: str
    route_snapshot: bytes
    state: DeliveryState
    attempts_started: int
    created_at: datetime
    updated_at: datetime
    next_attempt_at: datetime
    lease_token: UUID | None = None
    lease_expires_at: datetime | None = None
    replay_of: UUID | None = None
    replay_actor: str | None = None
    replay_reason: str | None = None

    def __post_init__(self) -> None:
        for identity in (self.delivery_id, self.tenant_id, self.event_id):
            if not isinstance(identity, UUID):
                raise FastAPIEffectsConfigurationError("Delivery identities must be UUID values.")
        for name, key in (
            ("route key", self.route_key),
            ("destination kind", self.destination_kind),
            ("destination key", self.destination_key),
        ):
            if not isinstance(key, str) or not _KEY.fullmatch(key):
                raise FastAPIEffectsConfigurationError(f"Delivery {name} is invalid.")
        if not _positive(self.route_version):
            raise FastAPIEffectsConfigurationError("Delivery route version must be positive.")
        if not isinstance(self.attempts_started, int) or isinstance(self.attempts_started, bool):
            raise FastAPIEffectsConfigurationError("Delivery attempts_started is invalid.")
        if self.attempts_started < 0:
            raise FastAPIEffectsConfigurationError("Delivery attempts_started cannot be negative.")
        if not isinstance(self.route_snapshot, bytes) or not self.route_snapshot:
            raise FastAPIEffectsConfigurationError(
                "Delivery route snapshot must be immutable bytes."
            )
        if not isinstance(self.state, DeliveryState):
            raise FastAPIEffectsConfigurationError("Delivery state is invalid.")
        for name, value in (
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
            ("next_attempt_at", self.next_attempt_at),
        ):
            _aware(name, value)
        if (self.lease_token is None) != (self.lease_expires_at is None):
            raise FastAPIEffectsConfigurationError(
                "Delivery lease token and expiry must be paired."
            )
        if self.state is DeliveryState.LEASED and self.lease_token is None:
            raise FastAPIEffectsConfigurationError("A leased delivery requires a lease token.")
        if self.state is not DeliveryState.LEASED and self.lease_token is not None:
            raise FastAPIEffectsConfigurationError(
                "Only a leased delivery may retain a lease token."
            )
        if self.replay_of is None:
            if self.replay_actor is not None or self.replay_reason is not None:
                raise FastAPIEffectsConfigurationError(
                    "Original delivery cannot contain replay audit data."
                )
        elif (
            not isinstance(self.replay_of, UUID)
            or self.replay_of == self.delivery_id
            or not isinstance(self.replay_actor, str)
            or not self.replay_actor
            or len(self.replay_actor) > 512
            or not isinstance(self.replay_reason, str)
            or not _KEY.fullmatch(self.replay_reason)
        ):
            raise FastAPIEffectsConfigurationError("Replay requires a bounded actor and reason.")
        if self.updated_at < self.created_at:
            raise FastAPIEffectsConfigurationError("Delivery updated before it was created.")


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_id: UUID
    tenant_id: UUID
    delivery_id: UUID
    attempt_number: int
    lease_token: UUID
    outcome: AttemptOutcome
    started_at: datetime
    finished_at: datetime | None = None
    failure_code: str | None = None
    failure_summary: str | None = None

    def __post_init__(self) -> None:
        for identity in (self.attempt_id, self.tenant_id, self.delivery_id, self.lease_token):
            if not isinstance(identity, UUID):
                raise FastAPIEffectsConfigurationError("Attempt identities must be UUID values.")
        if not _positive(self.attempt_number):
            raise FastAPIEffectsConfigurationError("Attempt number must be positive.")
        if not isinstance(self.outcome, AttemptOutcome):
            raise FastAPIEffectsConfigurationError("Attempt outcome is invalid.")
        _aware("started_at", self.started_at)
        if self.outcome is AttemptOutcome.STARTED:
            if (
                self.finished_at is not None
                or self.failure_code is not None
                or self.failure_summary is not None
            ):
                raise FastAPIEffectsConfigurationError(
                    "A started attempt cannot contain an outcome."
                )
        elif self.finished_at is None:
            raise FastAPIEffectsConfigurationError("A completed attempt requires finished_at.")
        if self.outcome is AttemptOutcome.SUCCEEDED and (
            self.failure_code is not None or self.failure_summary is not None
        ):
            raise FastAPIEffectsConfigurationError("A successful attempt cannot contain a failure.")
        if self.outcome not in {AttemptOutcome.STARTED, AttemptOutcome.SUCCEEDED} and (
            self.failure_code is None or self.failure_summary is None
        ):
            raise FastAPIEffectsConfigurationError(
                "A failed attempt requires bounded failure metadata."
            )
        if self.finished_at is not None:
            _aware("finished_at", self.finished_at)
            if self.finished_at < self.started_at:
                raise FastAPIEffectsConfigurationError("Attempt finished before it started.")
        if self.failure_code is not None and (
            not isinstance(self.failure_code, str) or not _KEY.fullmatch(self.failure_code)
        ):
            raise FastAPIEffectsConfigurationError("Attempt failure code is invalid.")
        if self.failure_summary is not None and (
            not isinstance(self.failure_summary, str) or len(self.failure_summary) > 512
        ):
            raise FastAPIEffectsConfigurationError("Attempt failure summary is invalid.")


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _aware(name: str, value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise FastAPIEffectsConfigurationError(f"Delivery {name} must be timezone-aware.")


__all__ = ["AttemptOutcome", "AttemptRecord", "DeliveryRecord", "DeliveryState"]

"""Bounded active/retiring/revoked delegation key lifecycle."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from fastapi_effects.delegation.audit import (
    DelegationAuditEvent,
    DelegationAuditOutcome,
    NoOpDelegationAuditSink,
)
from fastapi_effects.errors import FastAPIEffectsConfigurationError

_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class _AuditSink(Protocol):
    def record(self, event: DelegationAuditEvent) -> None: ...


class SigningKeyState(StrEnum):
    ACTIVE = "active"
    RETIRING = "retiring"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class SigningKey:
    key_id: str
    secret: bytes = field(repr=False)
    state: SigningKeyState = SigningKeyState.ACTIVE
    retired_at: datetime | None = None
    verify_until: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise FastAPIEffectsConfigurationError("Delegation signing key ID is invalid.")
        if not isinstance(self.secret, bytes) or not 32 <= len(self.secret) <= 128:
            raise FastAPIEffectsConfigurationError("Delegation signing key material is invalid.")
        if not isinstance(self.state, SigningKeyState):
            raise FastAPIEffectsConfigurationError("Delegation signing key state is invalid.")
        for value in (self.retired_at, self.verify_until):
            if value is not None and (
                not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None
            ):
                raise FastAPIEffectsConfigurationError("Delegation key retirement time is invalid.")
        if self.state is SigningKeyState.RETIRING and (
            self.retired_at is None
            or self.verify_until is None
            or self.verify_until <= self.retired_at
        ):
            raise FastAPIEffectsConfigurationError(
                "A retiring key requires a valid overlap interval."
            )
        if self.state is not SigningKeyState.RETIRING and (
            self.retired_at is not None or self.verify_until is not None
        ):
            raise FastAPIEffectsConfigurationError("Only retiring keys accept retirement times.")


class InMemoryKeyRing:
    """Process-local active/retiring/revoked key manager with bounded overlap."""

    def __init__(
        self,
        keys: tuple[SigningKey, ...],
        *,
        maximum_overlap: timedelta = timedelta(minutes=10),
        audit: _AuditSink | None = None,
    ) -> None:
        if not keys or len(keys) > 16:
            raise FastAPIEffectsConfigurationError("Delegation key ring size is invalid.")
        by_id = {key.key_id: key for key in keys}
        if len(by_id) != len(keys):
            raise FastAPIEffectsConfigurationError("Delegation key ring repeats a key ID.")
        if sum(key.state is SigningKeyState.ACTIVE for key in keys) != 1:
            raise FastAPIEffectsConfigurationError(
                "Delegation key ring requires exactly one active key."
            )
        if (
            not isinstance(maximum_overlap, timedelta)
            or maximum_overlap < timedelta(seconds=1)
            or maximum_overlap > timedelta(hours=1)
        ):
            raise FastAPIEffectsConfigurationError("Delegation key overlap policy is invalid.")
        if any(
            key.state is SigningKeyState.RETIRING
            and key.retired_at is not None
            and key.verify_until is not None
            and key.verify_until - key.retired_at > maximum_overlap
            for key in keys
        ):
            raise FastAPIEffectsConfigurationError("Delegation retiring key overlap is excessive.")
        self._keys = by_id
        self._maximum_overlap = maximum_overlap
        self._audit = audit or NoOpDelegationAuditSink()

    def signing_key(self, now: datetime) -> SigningKey:
        _aware(now)
        active = [key for key in self._keys.values() if key.state is SigningKeyState.ACTIVE]
        if len(active) != 1:
            raise FastAPIEffectsConfigurationError(
                "Delegation signing is disabled without an active key."
            )
        return active[0]

    def verification_key(self, key_id: str, now: datetime) -> SigningKey | None:
        _aware(now)
        key = self._keys.get(key_id)
        if key is None or key.state is SigningKeyState.REVOKED:
            return None
        if (
            key.state is SigningKeyState.RETIRING
            and key.verify_until is not None
            and now >= key.verify_until
        ):
            return None
        return key

    def rotate(
        self,
        new_key: SigningKey,
        *,
        now: datetime,
        overlap: timedelta,
        trace_id: str | None = None,
    ) -> None:
        _aware(now)
        if new_key.state is not SigningKeyState.ACTIVE or new_key.key_id in self._keys:
            raise FastAPIEffectsConfigurationError(
                "Delegation rotation key is invalid or repeated."
            )
        if len(self._keys) >= 16:
            raise FastAPIEffectsConfigurationError("Delegation key ring size is invalid.")
        if (
            not isinstance(overlap, timedelta)
            or overlap < timedelta(seconds=1)
            or overlap > self._maximum_overlap
        ):
            raise FastAPIEffectsConfigurationError("Delegation rotation overlap is invalid.")
        old = self.signing_key(now)
        self._keys[old.key_id] = replace(
            old,
            state=SigningKeyState.RETIRING,
            retired_at=now,
            verify_until=now + overlap,
        )
        self._keys[new_key.key_id] = new_key
        self._audit.record(
            _key_event(
                now=now,
                outcome=DelegationAuditOutcome.KEY_ROTATED,
                key_id=new_key.key_id,
                trace_id=trace_id,
            )
        )

    def revoke(
        self,
        key_id: str,
        *,
        now: datetime,
        trace_id: str | None = None,
    ) -> None:
        _aware(now)
        key = self._keys.get(key_id)
        if key is None:
            raise FastAPIEffectsConfigurationError("Delegation revocation key is unknown.")
        if key.state is SigningKeyState.REVOKED:
            return
        self._keys[key_id] = replace(
            key,
            state=SigningKeyState.REVOKED,
            retired_at=None,
            verify_until=None,
        )
        self._audit.record(
            _key_event(
                now=now,
                outcome=DelegationAuditOutcome.KEY_REVOKED,
                key_id=key_id,
                trace_id=trace_id,
            )
        )


def _aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise FastAPIEffectsConfigurationError(
            "Delegation key operation time must be timezone-aware."
        )


def _key_event(
    *,
    now: datetime,
    outcome: DelegationAuditOutcome,
    key_id: str,
    trace_id: str | None,
) -> DelegationAuditEvent:
    return DelegationAuditEvent(
        occurred_at=now,
        outcome=outcome,
        tenant_id=None,
        subject_id=None,
        audience="delegation-keyring",
        target_id=key_id,
        scopes=(),
        key_id=key_id,
        trace_id=trace_id,
    )


__all__ = ["InMemoryKeyRing", "SigningKey", "SigningKeyState"]

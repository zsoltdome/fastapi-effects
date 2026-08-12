"""Protocols for delegation signing keys and audit consumers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from fastapi_mergen.delegation.audit import DelegationAuditEvent
from fastapi_mergen.delegation.keys import SigningKey


class DelegationKeyRing(Protocol):
    def signing_key(self, now: datetime) -> SigningKey: ...

    def verification_key(self, key_id: str, now: datetime) -> SigningKey | None: ...


class DelegationKeyManager(DelegationKeyRing, Protocol):
    def rotate(
        self,
        new_key: SigningKey,
        *,
        now: datetime,
        overlap: timedelta,
        trace_id: str | None = None,
    ) -> None: ...

    def revoke(
        self,
        key_id: str,
        *,
        now: datetime,
        trace_id: str | None = None,
    ) -> None: ...


class DelegationAuditSink(Protocol):
    def record(self, event: DelegationAuditEvent) -> None: ...


__all__ = ["DelegationAuditSink", "DelegationKeyManager", "DelegationKeyRing"]

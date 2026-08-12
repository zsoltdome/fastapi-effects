"""Token-free bounded delegation audit records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError

_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class DelegationAuditOutcome(StrEnum):
    ISSUED = "issued"
    ALLOWED = "allowed"
    DENIED = "denied"
    KEY_ROTATED = "key_rotated"
    KEY_REVOKED = "key_revoked"


@dataclass(frozen=True, slots=True)
class DelegationAuditEvent:
    occurred_at: datetime
    outcome: DelegationAuditOutcome
    tenant_id: UUID | None
    subject_id: str | None
    audience: str
    target_id: str
    scopes: tuple[str, ...]
    key_id: str | None
    actor_id: str | None = None
    client_id: str | None = None
    token_id: UUID | None = None
    delegation_depth: int | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.occurred_at, datetime)
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
        ):
            raise MergenConfigurationError("Delegation audit time must be timezone-aware.")
        if not isinstance(self.outcome, DelegationAuditOutcome):
            raise MergenConfigurationError("Delegation audit outcome is invalid.")
        for value in (
            self.subject_id,
            self.actor_id,
            self.client_id,
            self.audience,
            self.target_id,
            self.key_id,
            self.trace_id,
        ):
            if value is not None and (not isinstance(value, str) or not _VALUE.fullmatch(value)):
                raise MergenConfigurationError("Delegation audit identity is invalid.")
        if self.tenant_id is not None and not isinstance(self.tenant_id, UUID):
            raise MergenConfigurationError("Delegation audit tenant is invalid.")
        if self.token_id is not None and not isinstance(self.token_id, UUID):
            raise MergenConfigurationError("Delegation audit token ID is invalid.")
        if (
            not isinstance(self.scopes, tuple)
            or len(self.scopes) > 128
            or any(
                not isinstance(scope, str) or not _VALUE.fullmatch(scope) for scope in self.scopes
            )
        ):
            raise MergenConfigurationError("Delegation audit scopes are invalid.")
        normalized_scopes = tuple(sorted(set(self.scopes)))
        if self.delegation_depth is not None and (
            not isinstance(self.delegation_depth, int)
            or isinstance(self.delegation_depth, bool)
            or not 1 <= self.delegation_depth <= 16
        ):
            raise MergenConfigurationError("Delegation audit depth is invalid.")
        object.__setattr__(self, "scopes", normalized_scopes)


class NoOpDelegationAuditSink:
    def record(self, event: DelegationAuditEvent) -> None:
        del event


def delegation_target_id(method: object, path: object) -> str:
    """Return a bounded audit identifier without retaining the raw target."""
    representation = f"{method!s}\0{path!s}".encode("utf-8", errors="replace")
    return f"target:{hashlib.sha256(representation).hexdigest()}"


__all__ = [
    "DelegationAuditEvent",
    "DelegationAuditOutcome",
    "NoOpDelegationAuditSink",
    "delegation_target_id",
]

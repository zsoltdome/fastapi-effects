"""Milestone 1 principal value used by the public API spike."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError


@dataclass(frozen=True, slots=True)
class Principal:
    """Trusted tenant and identity context supplied by the host application."""

    tenant_id: UUID
    subject_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    actor_id: str | None = None
    client_id: str | None = None
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    credential_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise MergenConfigurationError("Principal subject_id must not be blank.")
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise MergenConfigurationError("Principal expires_at must be after issued_at.")

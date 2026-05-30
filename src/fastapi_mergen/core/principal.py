"""Immutable principal value used by the public API spike."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError

_SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_SCOPES = 256
_MAX_ID_LENGTH = 512


def _validate_identifier(*, name: str, value: str | None) -> None:
    if value is None:
        return
    if not value.strip() or value != value.strip() or len(value) > _MAX_ID_LENGTH:
        raise MergenConfigurationError(
            f"Principal {name} must be non-blank, trimmed, and at most {_MAX_ID_LENGTH} characters."
        )


def _require_aware(name: str, value: datetime | None) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise MergenConfigurationError(f"Principal {name} must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class Principal:
    """Trusted tenant and identity context supplied by the host application.

    This Milestone 1 value exercises the public shape. Durable canonical
    serialization and secret-field rejection are implemented in Milestone 2.
    """

    tenant_id: UUID
    subject_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    actor_id: str | None = None
    client_id: str | None = None
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    authentication_time: datetime | None = None
    expires_at: datetime | None = None
    credential_ref: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(name="subject_id", value=self.subject_id)
        _validate_identifier(name="actor_id", value=self.actor_id)
        _validate_identifier(name="client_id", value=self.client_id)
        _validate_identifier(name="credential_ref", value=self.credential_ref)
        _require_aware("issued_at", self.issued_at)
        _require_aware("authentication_time", self.authentication_time)
        _require_aware("expires_at", self.expires_at)

        normalized_scopes = frozenset(self.scopes)
        if len(normalized_scopes) > _MAX_SCOPES:
            raise MergenConfigurationError(
                f"Principal scopes may contain at most {_MAX_SCOPES} items."
            )
        invalid = sorted(scope for scope in normalized_scopes if not _SCOPE_PATTERN.fullmatch(scope))
        if invalid:
            raise MergenConfigurationError("Principal contains an invalid scope name.")
        object.__setattr__(self, "scopes", normalized_scopes)

        if self.authentication_time is not None and self.authentication_time > self.issued_at:
            raise MergenConfigurationError(
                "Principal authentication_time must not be after issued_at."
            )
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise MergenConfigurationError("Principal expires_at must be after issued_at.")

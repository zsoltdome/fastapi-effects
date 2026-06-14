"""Immutable principal value used by the public API spike."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from fastapi_mergen.errors import MergenConfigurationError

_SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_SCOPES = 256
_MAX_ID_LENGTH = 512


def _validate_identifier(*, name: str, value: object) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise MergenConfigurationError(f"Principal {name} must be a string or None.")
    if not value.strip() or value != value.strip() or len(value) > _MAX_ID_LENGTH:
        raise MergenConfigurationError(
            f"Principal {name} must be non-blank, trimmed, and at most {_MAX_ID_LENGTH} characters."
        )


def _require_aware(name: str, value: object) -> None:
    if value is None:
        return
    if not isinstance(value, datetime):
        raise MergenConfigurationError(f"Principal {name} must be a datetime or None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise MergenConfigurationError(f"Principal {name} must be timezone-aware.")


def _normalize_scopes(scopes: object) -> frozenset[str]:
    if isinstance(scopes, (str, bytes)) or not isinstance(scopes, Iterable):
        raise MergenConfigurationError("Principal scopes must be an iterable of strings.")
    try:
        normalized = frozenset(scopes)
    except TypeError as exc:
        raise MergenConfigurationError(
            "Principal scopes must contain hashable strings."
        ) from exc
    if len(normalized) > _MAX_SCOPES:
        raise MergenConfigurationError(
            f"Principal scopes may contain at most {_MAX_SCOPES} items."
        )
    if any(
        not isinstance(scope, str) or not _SCOPE_PATTERN.fullmatch(scope)
        for scope in normalized
    ):
        raise MergenConfigurationError("Principal contains an invalid scope name.")
    return normalized


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
        if not isinstance(self.tenant_id, UUID):
            raise MergenConfigurationError("Principal tenant_id must be a UUID.")
        _validate_identifier(name="subject_id", value=self.subject_id)
        _validate_identifier(name="actor_id", value=self.actor_id)
        _validate_identifier(name="client_id", value=self.client_id)
        _validate_identifier(name="credential_ref", value=self.credential_ref)
        _require_aware("issued_at", self.issued_at)
        _require_aware("authentication_time", self.authentication_time)
        _require_aware("expires_at", self.expires_at)

        normalized_scopes = _normalize_scopes(self.scopes)
        object.__setattr__(self, "scopes", normalized_scopes)

        if self.authentication_time is not None and self.authentication_time > self.issued_at:
            raise MergenConfigurationError(
                "Principal authentication_time must not be after issued_at."
            )
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise MergenConfigurationError("Principal expires_at must be after issued_at.")

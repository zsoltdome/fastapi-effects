"""Immutable, durable, secret-minimizing principal values."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi_effects.errors import FastAPIEffectsConfigurationError

_SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_MAX_SCOPES = 256
_MAX_ID_LENGTH = 512
_ENVELOPE_FIELDS = frozenset(
    {
        "tenant_id",
        "subject_id",
        "scopes",
        "actor_id",
        "client_id",
        "issued_at",
        "authentication_time",
        "expires_at",
        "credential_ref",
    }
)
_RAW_CREDENTIAL_FIELDS = frozenset(
    {
        "authorization",
        "proxy_authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "session",
        "session_token",
    }
)


def _validate_identifier(*, name: str, value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_ID_LENGTH
        or _CONTROL_CHARACTER_PATTERN.search(value) is not None
    ):
        raise FastAPIEffectsConfigurationError(
            f"Principal {name} must be a safe, trimmed string of at most "
            f"{_MAX_ID_LENGTH} characters."
        )


def _require_aware(name: str, value: object, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, datetime):
        raise FastAPIEffectsConfigurationError(f"Principal {name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise FastAPIEffectsConfigurationError(f"Principal {name} must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class Principal:
    """Trusted tenant and identity context supplied by the host application.

    Raw authentication material is deliberately absent. ``credential_ref`` is an
    opaque host-owned lookup reference and is excluded from ``repr``.
    """

    tenant_id: UUID
    subject_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    actor_id: str | None = None
    client_id: str | None = None
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    authentication_time: datetime | None = None
    expires_at: datetime | None = None
    credential_ref: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise FastAPIEffectsConfigurationError("Principal tenant_id must be a UUID.")
        _validate_identifier(name="subject_id", value=self.subject_id)
        _validate_identifier(name="actor_id", value=self.actor_id)
        _validate_identifier(name="client_id", value=self.client_id)
        _validate_identifier(name="credential_ref", value=self.credential_ref)
        _require_aware("issued_at", self.issued_at)
        _require_aware("authentication_time", self.authentication_time, optional=True)
        _require_aware("expires_at", self.expires_at, optional=True)

        scope_value: object = self.scopes
        if isinstance(scope_value, str):
            raise FastAPIEffectsConfigurationError(
                "Principal scopes must be a collection of strings."
            )
        try:
            normalized_scopes = frozenset(self.scopes)
        except TypeError as exc:
            raise FastAPIEffectsConfigurationError(
                "Principal scopes must be an iterable of hashable strings."
            ) from exc
        if len(normalized_scopes) > _MAX_SCOPES:
            raise FastAPIEffectsConfigurationError(
                f"Principal scopes may contain at most {_MAX_SCOPES} items."
            )
        if any(
            not isinstance(scope, str) or not _SCOPE_PATTERN.fullmatch(scope)
            for scope in normalized_scopes
        ):
            raise FastAPIEffectsConfigurationError("Principal contains an invalid scope name.")
        object.__setattr__(self, "scopes", normalized_scopes)

        if self.authentication_time is not None and self.authentication_time > self.issued_at:
            raise FastAPIEffectsConfigurationError(
                "Principal authentication_time must not be after issued_at."
            )
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise FastAPIEffectsConfigurationError("Principal expires_at must be after issued_at.")

    def to_envelope(self) -> PrincipalEnvelope:
        """Create the detached durable representation stored with event intent."""
        return PrincipalEnvelope(
            tenant_id=self.tenant_id,
            subject_id=self.subject_id,
            scopes=tuple(sorted(self.scopes)),
            actor_id=self.actor_id,
            client_id=self.client_id,
            issued_at=self.issued_at,
            authentication_time=self.authentication_time,
            expires_at=self.expires_at,
            credential_ref=self.credential_ref,
        )

    @classmethod
    def from_envelope(cls, envelope: PrincipalEnvelope | Mapping[str, object]) -> Principal:
        """Restore a validated principal without accepting credential-like extras."""
        normalized = (
            envelope
            if isinstance(envelope, PrincipalEnvelope)
            else PrincipalEnvelope.from_dict(envelope)
        )
        return cls(
            tenant_id=normalized.tenant_id,
            subject_id=normalized.subject_id,
            scopes=frozenset(normalized.scopes),
            actor_id=normalized.actor_id,
            client_id=normalized.client_id,
            issued_at=normalized.issued_at,
            authentication_time=normalized.authentication_time,
            expires_at=normalized.expires_at,
            credential_ref=normalized.credential_ref,
        )


@dataclass(frozen=True, slots=True)
class PrincipalEnvelope:
    """JSON-safe immutable authority provenance attached to an event."""

    tenant_id: UUID
    subject_id: str
    scopes: tuple[str, ...]
    actor_id: str | None
    client_id: str | None
    issued_at: datetime
    authentication_time: datetime | None
    expires_at: datetime | None
    credential_ref: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        principal = Principal(
            tenant_id=self.tenant_id,
            subject_id=self.subject_id,
            scopes=frozenset(self.scopes),
            actor_id=self.actor_id,
            client_id=self.client_id,
            issued_at=self.issued_at,
            authentication_time=self.authentication_time,
            expires_at=self.expires_at,
            credential_ref=self.credential_ref,
        )
        object.__setattr__(self, "scopes", tuple(sorted(principal.scopes)))

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": str(self.tenant_id),
            "subject_id": self.subject_id,
            "scopes": list(self.scopes),
            "actor_id": self.actor_id,
            "client_id": self.client_id,
            "issued_at": _format_time(self.issued_at),
            "authentication_time": _format_optional_time(self.authentication_time),
            "expires_at": _format_optional_time(self.expires_at),
            "credential_ref": self.credential_ref,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> PrincipalEnvelope:
        if not isinstance(value, Mapping):
            raise FastAPIEffectsConfigurationError("Principal envelope must be an object.")
        keys = set(value)
        if keys & _RAW_CREDENTIAL_FIELDS or keys != _ENVELOPE_FIELDS:
            raise FastAPIEffectsConfigurationError(
                "Principal envelope contains unsupported fields."
            )
        scopes = value["scopes"]
        if isinstance(scopes, str) or not isinstance(scopes, (list, tuple)):
            raise FastAPIEffectsConfigurationError("Principal envelope scopes are invalid.")
        try:
            return cls(
                tenant_id=UUID(_require_string(value["tenant_id"])),
                subject_id=_require_string(value["subject_id"]),
                scopes=tuple(_require_string(scope) for scope in scopes),
                actor_id=_optional_string(value["actor_id"]),
                client_id=_optional_string(value["client_id"]),
                issued_at=_parse_time(value["issued_at"]),
                authentication_time=_parse_optional_time(value["authentication_time"]),
                expires_at=_parse_optional_time(value["expires_at"]),
                credential_ref=_optional_string(value["credential_ref"]),
            )
        except (ValueError, TypeError) as exc:
            raise FastAPIEffectsConfigurationError("Principal envelope is invalid.") from exc


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _format_optional_time(value: datetime | None) -> str | None:
    return None if value is None else _format_time(value)


def _parse_time(value: object) -> datetime:
    text = _require_string(value)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    _require_aware("envelope time", parsed)
    return parsed


def _parse_optional_time(value: object) -> datetime | None:
    return None if value is None else _parse_time(value)


def _require_string(value: object) -> str:
    if not isinstance(value, str):
        raise FastAPIEffectsConfigurationError("Principal envelope field must be text.")
    return value


def _optional_string(value: object) -> str | None:
    return None if value is None else _require_string(value)


__all__ = ["Principal", "PrincipalEnvelope"]

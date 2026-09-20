"""Bounded versioned delegation claim model."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi_effects.delegation.targets import canonical_method, canonical_target_path
from fastapi_effects.errors import FastAPIEffectsConfigurationError

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FIELDS = frozenset(
    {
        "version",
        "issuer",
        "tenant_id",
        "subject_id",
        "actor_id",
        "client_id",
        "audience",
        "method",
        "path",
        "scopes",
        "issued_at",
        "not_before",
        "expires_at",
        "token_id",
        "key_id",
        "delegation_depth",
    }
)
_MAXIMUM_CREDENTIAL_LIFETIME_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class DelegationClaims:
    version: int
    issuer: str
    tenant_id: UUID
    subject_id: str
    actor_id: str | None
    client_id: str | None
    audience: str
    method: str
    path: str
    scopes: tuple[str, ...]
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    token_id: UUID
    key_id: str
    delegation_depth: int = 1

    def __post_init__(self) -> None:
        if self.version != 1:
            raise FastAPIEffectsConfigurationError("Delegation claim version is unsupported.")
        for name, value in (
            ("issuer", self.issuer),
            ("subject", self.subject_id),
            ("audience", self.audience),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise FastAPIEffectsConfigurationError(f"Delegation {name} is invalid.")
        optional_identities: tuple[tuple[str, object], ...] = (
            ("actor", self.actor_id),
            ("client", self.client_id),
        )
        for optional_name, optional_value in optional_identities:
            if optional_value is not None and (
                not isinstance(optional_value, str) or not _IDENTIFIER.fullmatch(optional_value)
            ):
                raise FastAPIEffectsConfigurationError(f"Delegation {optional_name} is invalid.")
        if not isinstance(self.tenant_id, UUID) or not isinstance(self.token_id, UUID):
            raise FastAPIEffectsConfigurationError("Delegation UUID identity is invalid.")
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise FastAPIEffectsConfigurationError("Delegation key ID is invalid.")
        object.__setattr__(self, "method", canonical_method(self.method))
        object.__setattr__(self, "path", canonical_target_path(self.path))
        scope_value: object = self.scopes
        if isinstance(scope_value, str) or not isinstance(scope_value, tuple):
            raise FastAPIEffectsConfigurationError("Delegation scopes must be a collection.")
        if len(self.scopes) > 128 or any(
            not isinstance(scope, str) or not _SCOPE.fullmatch(scope) for scope in self.scopes
        ):
            raise FastAPIEffectsConfigurationError("Delegation scope set is invalid.")
        normalized = tuple(sorted(set(self.scopes)))
        object.__setattr__(self, "scopes", normalized)
        for name, timestamp in (
            ("issued_at", self.issued_at),
            ("not_before", self.not_before),
            ("expires_at", self.expires_at),
        ):
            if (
                not isinstance(timestamp, datetime)
                or timestamp.tzinfo is None
                or timestamp.utcoffset() is None
            ):
                raise FastAPIEffectsConfigurationError(f"Delegation {name} must be timezone-aware.")
        if self.not_before < self.issued_at or self.expires_at <= self.not_before:
            raise FastAPIEffectsConfigurationError("Delegation validity interval is invalid.")
        if (
            self.expires_at - self.issued_at
        ).total_seconds() > _MAXIMUM_CREDENTIAL_LIFETIME_SECONDS:
            raise FastAPIEffectsConfigurationError("Delegation credential lifetime is excessive.")
        if (
            not isinstance(self.delegation_depth, int)
            or isinstance(self.delegation_depth, bool)
            or not 1 <= self.delegation_depth <= 16
        ):
            raise FastAPIEffectsConfigurationError("Delegation depth is invalid.")

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "issuer": self.issuer,
            "tenant_id": str(self.tenant_id),
            "subject_id": self.subject_id,
            "actor_id": self.actor_id,
            "client_id": self.client_id,
            "audience": self.audience,
            "method": self.method,
            "path": self.path,
            "scopes": list(self.scopes),
            "issued_at": _epoch(self.issued_at),
            "not_before": _epoch(self.not_before),
            "expires_at": _epoch(self.expires_at),
            "token_id": str(self.token_id),
            "key_id": self.key_id,
            "delegation_depth": self.delegation_depth,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DelegationClaims:
        if not isinstance(value, Mapping) or set(value) != _FIELDS:
            raise FastAPIEffectsConfigurationError("Delegation claims are incomplete or unknown.")
        scopes = value["scopes"]
        if not isinstance(scopes, list) or any(not isinstance(item, str) for item in scopes):
            raise FastAPIEffectsConfigurationError("Delegation scopes are invalid.")
        try:
            return cls(
                version=_integer(value["version"]),
                issuer=_string(value["issuer"]),
                tenant_id=UUID(_string(value["tenant_id"])),
                subject_id=_string(value["subject_id"]),
                actor_id=_optional_string(value["actor_id"]),
                client_id=_optional_string(value["client_id"]),
                audience=_string(value["audience"]),
                method=_string(value["method"]),
                path=_string(value["path"]),
                scopes=tuple(scopes),
                issued_at=_time(value["issued_at"]),
                not_before=_time(value["not_before"]),
                expires_at=_time(value["expires_at"]),
                token_id=UUID(_string(value["token_id"])),
                key_id=_string(value["key_id"]),
                delegation_depth=_integer(value["delegation_depth"]),
            )
        except (TypeError, ValueError) as exc:
            raise FastAPIEffectsConfigurationError("Delegation claims are invalid.") from exc


def _epoch(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp())


def _time(value: object) -> datetime:
    return datetime.fromtimestamp(_integer(value), tz=UTC)


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_string(value: object) -> str | None:
    return None if value is None else _string(value)


__all__ = ["DelegationClaims"]

"""Fixed PostgreSQL role contract for migrations and diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi_mergen.errors import MergenConfigurationError

MIGRATION_ROLE = "mergen_migration"
APPLICATION_ROLE = "mergen_app"
RELAY_ROLE = "mergen_relay"
_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


@dataclass(frozen=True, slots=True)
class RuntimeRoles:
    migration: str = MIGRATION_ROLE
    application: str = APPLICATION_ROLE
    relay: str = RELAY_ROLE

    def __post_init__(self) -> None:
        for role in (self.migration, self.application, self.relay):
            if not isinstance(role, str) or not _ROLE.fullmatch(role):
                raise MergenConfigurationError("PostgreSQL role name is invalid.")
        if len({self.migration, self.application, self.relay}) != 3:
            raise MergenConfigurationError("PostgreSQL runtime roles must be distinct.")


def create_role_sql(role: str) -> str:
    if not _ROLE.fullmatch(role):
        raise MergenConfigurationError("PostgreSQL role name is invalid.")
    return (
        "DO $role$ BEGIN "
        f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
        f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; "
        "END IF; END $role$"
    )


__all__ = [
    "APPLICATION_ROLE",
    "MIGRATION_ROLE",
    "RELAY_ROLE",
    "RuntimeRoles",
    "create_role_sql",
]

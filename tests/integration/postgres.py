"""Disposable PostgreSQL database and role fixture for integration tests."""

from __future__ import annotations

import os
import re
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"unsafe generated PostgreSQL identifier: {value!r}")
    return f'"{value}"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _dsn_with_credentials(admin_dsn: str, *, user: str, password: str, database: str) -> str:
    parsed = urlsplit(admin_dsn)
    host = parsed.hostname or "127.0.0.1"
    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}{port}"
    return urlunsplit((parsed.scheme, netloc, f"/{database}", parsed.query, ""))


def sqlalchemy_async_dsn(dsn: str) -> str:
    """Convert a PostgreSQL DSN into the explicit SQLAlchemy asyncpg scheme."""
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("integration DSN must use postgres or postgresql")
    return urlunsplit(("postgresql+asyncpg", parsed.netloc, parsed.path, parsed.query, ""))


@dataclass(frozen=True, slots=True)
class ProvisionedDatabase:
    """Isolated database with all roles required by the planned trust model."""

    admin_dsn: str
    database: str
    migration_role: str
    app_role: str
    relay_role: str
    misconfigured_role: str
    migration_dsn: str
    app_dsn: str
    relay_dsn: str
    misconfigured_dsn: str

    @property
    def migration_sqlalchemy_dsn(self) -> str:
        return sqlalchemy_async_dsn(self.migration_dsn)

    @property
    def app_sqlalchemy_dsn(self) -> str:
        return sqlalchemy_async_dsn(self.app_dsn)

    @property
    def relay_sqlalchemy_dsn(self) -> str:
        return sqlalchemy_async_dsn(self.relay_dsn)


async def _connect(dsn: str) -> Any:
    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover - actionable environment failure
        raise RuntimeError('Install test dependencies with "fastapi-mergen[test]".') from exc
    return await asyncpg.connect(dsn)


async def _cleanup(admin_dsn: str, *, database: str, roles: tuple[str, ...]) -> None:
    connection = await _connect(admin_dsn)
    try:
        await connection.execute(
            f"DROP DATABASE IF EXISTS {_quote_identifier(database)} WITH (FORCE)"
        )
        for role in roles:
            await connection.execute(f"DROP ROLE IF EXISTS {_quote_identifier(role)}")
    finally:
        await connection.close()


@asynccontextmanager
async def provision_test_database(admin_dsn: str):
    """Create unique roles/database and remove them even after a failed test."""
    suffix = f"{os.getpid()}_{uuid4().hex[:10]}"
    database = f"mergen_test_{suffix}"
    migration_role = f"mergen_owner_{suffix}"
    app_role = f"mergen_app_{suffix}"
    relay_role = f"mergen_relay_{suffix}"
    misconfigured_role = f"mergen_bad_{suffix}"
    roles = (migration_role, app_role, relay_role, misconfigured_role)
    passwords = {role: secrets.token_urlsafe(24) for role in roles}

    admin = await _connect(admin_dsn)
    created_roles: list[str] = []
    database_created = False
    try:
        for role in roles:
            bypass = " BYPASSRLS" if role == misconfigured_role else " NOBYPASSRLS"
            await admin.execute(
                f"CREATE ROLE {_quote_identifier(role)} LOGIN PASSWORD "
                f"{_quote_literal(passwords[role])} NOSUPERUSER NOCREATEDB "
                f"NOCREATEROLE NOINHERIT{bypass}"
            )
            created_roles.append(role)
        await admin.execute(
            f"CREATE DATABASE {_quote_identifier(database)} "
            f"OWNER {_quote_identifier(migration_role)}"
        )
        database_created = True
        await admin.execute(f"REVOKE ALL ON DATABASE {_quote_identifier(database)} FROM PUBLIC")
        await admin.execute(
            f"GRANT CONNECT ON DATABASE {_quote_identifier(database)} TO "
            + ", ".join(_quote_identifier(role) for role in roles)
        )
    except BaseException:
        await admin.close()
        if database_created or created_roles:
            await _cleanup(admin_dsn, database=database, roles=tuple(created_roles))
        raise
    else:
        await admin.close()

    fixture = ProvisionedDatabase(
        admin_dsn=admin_dsn,
        database=database,
        migration_role=migration_role,
        app_role=app_role,
        relay_role=relay_role,
        misconfigured_role=misconfigured_role,
        migration_dsn=_dsn_with_credentials(
            admin_dsn,
            user=migration_role,
            password=passwords[migration_role],
            database=database,
        ),
        app_dsn=_dsn_with_credentials(
            admin_dsn,
            user=app_role,
            password=passwords[app_role],
            database=database,
        ),
        relay_dsn=_dsn_with_credentials(
            admin_dsn,
            user=relay_role,
            password=passwords[relay_role],
            database=database,
        ),
        misconfigured_dsn=_dsn_with_credentials(
            admin_dsn,
            user=misconfigured_role,
            password=passwords[misconfigured_role],
            database=database,
        ),
    )
    try:
        yield fixture
    finally:
        await _cleanup(admin_dsn, database=database, roles=roles)

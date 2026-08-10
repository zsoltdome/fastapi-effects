from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_mergen.core.event import Event
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.errors import CommandConflict, DedupeConflict, MergenConfigurationError
from fastapi_mergen.idempotency.command import CommandContext
from fastapi_mergen.idempotency.fingerprint import RequestFingerprint
from fastapi_mergen.idempotency.models import CommandIdentity, CommandRow
from fastapi_mergen.idempotency.responses import CapturedResponse
from fastapi_mergen.idempotency.store import CommandStore
from fastapi_mergen.postgres.command_schema import install_command_schema
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.postgres.store import PostgresStore
from fastapi_mergen.sqlalchemy.models import SCHEMA, EventRow
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration

_BUSINESS_TABLE = f"{SCHEMA}.command_test_business"


@dataclass(frozen=True, slots=True)
class _FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


def _fingerprint(value: bytes = b"same-request") -> RequestFingerprint:
    return RequestFingerprint(version=1, digest=hashlib.sha256(value).digest())


def _identity(principal: Principal, key: str = "command-key") -> CommandIdentity:
    return CommandIdentity.from_key(
        tenant_id=principal.tenant_id,
        route_id="invoice.create",
        method="POST",
        key=key,
    )


@pytest.mark.asyncio
async def test_concurrent_duplicate_commits_one_business_result_and_replays(
    test_database: ProvisionedDatabase,
) -> None:
    migration_engine, app_engine, relay_engine, sessions, _roles = await _setup(test_database)
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:alice")
    executions = 0

    async def submit() -> tuple[bool, bytes, int]:
        nonlocal executions
        async with sessions() as session:
            context = CommandContext(
                session=session,
                principal=principal,
                identity=_identity(principal),
                fingerprint=_fingerprint(),
            )
            async with context:
                generation = context.generation
                if context.replayed:
                    assert context.response is not None
                    return True, context.response.body, generation
                executions += 1
                await session.execute(
                    text(
                        f"INSERT INTO {_BUSINESS_TABLE}(tenant_id, business_key) "
                        "VALUES (:tenant, 'invoice:1')"
                    ),
                    {"tenant": tenant_id},
                )
                await asyncio.sleep(0.05)
                captured = await context.complete(
                    CapturedResponse(
                        status_code=201,
                        media_type="application/json",
                        body=b'{"invoice":"1"}',
                        headers={"etag": '"invoice-v1"'},
                    )
                )
                return False, captured.body, generation

    try:
        first, second = await asyncio.gather(submit(), submit())
        assert executions == 1
        assert {first[0], second[0]} == {False, True}
        assert first[1:] == second[1:]
        async with sessions() as session, session.begin():
            await _bind(session, principal)
            command_count = await session.scalar(select(func.count()).select_from(CommandRow))
            business_count = await session.scalar(text(f"SELECT count(*) FROM {_BUSINESS_TABLE}"))
        assert command_count == 1
        assert business_count == 1
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()


@pytest.mark.asyncio
async def test_rollback_conflict_expiry_trigger_rls_and_pruning(
    test_database: ProvisionedDatabase,
) -> None:
    migration_engine, app_engine, relay_engine, sessions, _roles = await _setup(test_database)
    relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:alice")
    identity = _identity(principal, "rollback-key")
    fingerprint = _fingerprint(b"rollback")
    started = datetime(2026, 8, 30, 10, tzinfo=UTC)

    async def roll_back_request() -> None:
        async with sessions() as session:
            context = CommandContext(
                session=session,
                principal=principal,
                identity=identity,
                fingerprint=fingerprint,
                clock=_FixedClock(started),
                ttl=timedelta(seconds=1),
            )
            async with context:
                await session.execute(
                    text(
                        f"INSERT INTO {_BUSINESS_TABLE}(tenant_id, business_key) "
                        "VALUES (:tenant, 'rolled-back')"
                    ),
                    {"tenant": tenant_id},
                )
                raise RuntimeError("rollback window")

    async def conflict_request(
        mismatched_principal: Principal,
        mismatched_fingerprint: RequestFingerprint,
    ) -> None:
        async with (
            sessions() as session,
            CommandContext(
                session=session,
                principal=mismatched_principal,
                identity=identity,
                fingerprint=mismatched_fingerprint,
                clock=_FixedClock(started),
                ttl=timedelta(seconds=1),
            ),
        ):
            pass

    async def mutate_completed_response() -> None:
        async with sessions() as session, session.begin():
            await _bind(session, principal)
            rows = (await session.scalars(select(CommandRow).order_by(CommandRow.generation))).all()
            assert [row.state for row in rows] == ["superseded", "completed"]
            rows[1].response_body = b"mutated"
            await session.flush()

    async def read_table_as_relay() -> None:
        async with relay_sessions() as session:
            await session.scalar(select(func.count()).select_from(CommandRow))

    try:
        with pytest.raises(RuntimeError, match="rollback window"):
            await roll_back_request()

        async with sessions() as session:
            context = CommandContext(
                session=session,
                principal=principal,
                identity=identity,
                fingerprint=fingerprint,
                clock=_FixedClock(started),
                ttl=timedelta(seconds=1),
            )
            async with context:
                await session.execute(
                    text(
                        f"INSERT INTO {_BUSINESS_TABLE}(tenant_id, business_key) "
                        "VALUES (:tenant, 'committed')"
                    ),
                    {"tenant": tenant_id},
                )
                await context.complete(CapturedResponse(200, "text/plain", b"generation-one"))
                assert context.generation == 1

        for mismatched_principal, mismatched_fingerprint in (
            (principal, _fingerprint(b"different")),
            (
                Principal(tenant_id=tenant_id, subject_id="user:bob"),
                fingerprint,
            ),
        ):
            with pytest.raises(CommandConflict):
                await conflict_request(mismatched_principal, mismatched_fingerprint)

        async with sessions() as session:
            context = CommandContext(
                session=session,
                principal=principal,
                identity=identity,
                fingerprint=_fingerprint(b"new-generation"),
                clock=_FixedClock(started + timedelta(seconds=2)),
                ttl=timedelta(seconds=1),
            )
            async with context:
                assert context.generation == 2
                await context.complete(CapturedResponse(200, "text/plain", b"generation-two"))

        with pytest.raises(DBAPIError):
            await mutate_completed_response()

        other = Principal(tenant_id=uuid4(), subject_id="user:other")
        async with sessions() as session, session.begin():
            await _bind(session, other)
            assert await session.scalar(select(func.count()).select_from(CommandRow)) == 0

        with pytest.raises(DBAPIError):
            await read_table_as_relay()

        async with relay_sessions() as session:
            deleted = await CommandStore().prune(
                session,
                before=started + timedelta(seconds=2),
                batch_size=1,
            )
        assert deleted == 1
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()


@pytest.mark.asyncio
async def test_missing_completion_rolls_back_claim(
    test_database: ProvisionedDatabase,
) -> None:
    migration_engine, app_engine, relay_engine, sessions, _roles = await _setup(test_database)
    principal = Principal(tenant_id=uuid4(), subject_id="user:missing")

    async def omit_completion() -> None:
        async with (
            sessions() as session,
            CommandContext(
                session=session,
                principal=principal,
                identity=_identity(principal, "missing-completion"),
                fingerprint=_fingerprint(b"missing"),
            ),
        ):
            await session.execute(
                text(
                    f"INSERT INTO {_BUSINESS_TABLE}(tenant_id, business_key) "
                    "VALUES (:tenant, 'must-rollback')"
                ),
                {"tenant": principal.tenant_id},
            )

    try:
        with pytest.raises(MergenConfigurationError, match="requires complete"):
            await omit_completion()
        async with sessions() as session, session.begin():
            await _bind(session, principal)
            assert await session.scalar(select(func.count()).select_from(CommandRow)) == 0
            assert await session.scalar(text(f"SELECT count(*) FROM {_BUSINESS_TABLE}")) == 0
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()


@pytest.mark.asyncio
async def test_effect_publication_failure_rolls_back_command_and_business_write(
    test_database: ProvisionedDatabase,
) -> None:
    migration_engine, app_engine, relay_engine, sessions, _roles = await _setup(test_database)
    principal = Principal(tenant_id=uuid4(), subject_id="user:effects")

    async def publish_conflicting_effect() -> None:
        async with sessions() as session:
            context = CommandContext(
                session=session,
                principal=principal,
                identity=_identity(principal, "effect-two"),
                fingerprint=_fingerprint(b"effect-two"),
                effect_store=PostgresStore(),
            )
            async with context:
                await session.execute(
                    text(
                        f"INSERT INTO {_BUSINESS_TABLE}(tenant_id, business_key) "
                        "VALUES (:tenant, 'effect-two')"
                    ),
                    {"tenant": principal.tenant_id},
                )
                await context.emit(
                    Event(type="invoice.command", version=1, data={"version": 2}),
                    dedupe_namespace="command-effect",
                    dedupe_key="invoice-one",
                )

    try:
        async with sessions() as session:
            context = CommandContext(
                session=session,
                principal=principal,
                identity=_identity(principal, "effect-one"),
                fingerprint=_fingerprint(b"effect-one"),
                effect_store=PostgresStore(),
            )
            async with context:
                await session.execute(
                    text(
                        f"INSERT INTO {_BUSINESS_TABLE}(tenant_id, business_key) "
                        "VALUES (:tenant, 'effect-one')"
                    ),
                    {"tenant": principal.tenant_id},
                )
                await context.emit(
                    Event(type="invoice.command", version=1, data={"version": 1}),
                    dedupe_namespace="command-effect",
                    dedupe_key="invoice-one",
                )
                await context.complete(CapturedResponse(201, "application/json", b"{}"))

        with pytest.raises(DedupeConflict):
            await publish_conflicting_effect()

        async with sessions() as session, session.begin():
            await _bind(session, principal)
            business_count = await session.scalar(text(f"SELECT count(*) FROM {_BUSINESS_TABLE}"))
            event_count = await session.scalar(select(func.count()).select_from(EventRow))
            command_count = await session.scalar(select(func.count()).select_from(CommandRow))
        assert (business_count, event_count, command_count) == (1, 1, 1)
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()


async def _setup(
    database: ProvisionedDatabase,
) -> tuple[
    AsyncEngine,
    AsyncEngine,
    AsyncEngine,
    async_sessionmaker[AsyncSession],
    RuntimeRoles,
]:
    migration_engine = create_async_engine(database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(database.relay_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=database.migration_role,
        application=database.app_role,
        relay=database.relay_role,
    )
    await install_core_schema(migration_engine, roles=roles)
    await install_command_schema(migration_engine, roles=roles)
    async with migration_engine.begin() as connection:
        await connection.execute(
            text(
                f"CREATE TABLE {_BUSINESS_TABLE} ("
                "tenant_id uuid NOT NULL, business_key text NOT NULL UNIQUE)"
            )
        )
        await connection.execute(
            text(f"GRANT SELECT, INSERT ON {_BUSINESS_TABLE} TO {roles.application}")
        )
    return (
        migration_engine,
        app_engine,
        relay_engine,
        async_sessionmaker(app_engine, expire_on_commit=False),
        roles,
    )


async def _bind(session: AsyncSession, principal: Principal) -> None:
    await session.execute(
        text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
        {"tenant": str(principal.tenant_id)},
    )
    await session.execute(
        text("SELECT set_config('mergen.subject_id', :subject, true)"),
        {"subject": principal.subject_id},
    )

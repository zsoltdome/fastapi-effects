from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from fastapi_effects import (
    AuthorizationMode,
    Event,
    FastAPIEffectsUnitOfWork,
    LeaseLost,
    Principal,
    RetryPolicy,
)
from fastapi_effects.core.delivery import DeliveryState
from fastapi_effects.core.routing import RouteSpecification
from fastapi_effects.postgres import PostgresStore
from fastapi_effects.postgres.leasing import ClaimedDelivery, LeaseRepository
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.sqlalchemy.models import AttemptRow, DeliveryRow, EventRow
from fastapi_effects.sqlalchemy.repository import (
    attempt_from_row,
    delivery_from_row,
    event_from_row,
)
from tests.integration.postgres import ProvisionedDatabase, sqlalchemy_async_dsn

pytestmark = [pytest.mark.integration, pytest.mark.chaos]


@dataclass(slots=True)
class _CommitAcknowledgementDropProxy:
    target_host: str
    target_port: int
    commit_seen: asyncio.Event = field(default_factory=asyncio.Event)
    acknowledgement_dropped: asyncio.Event = field(default_factory=asyncio.Event)
    _server: asyncio.Server | None = None
    _connections: set[asyncio.Task[None]] = field(default_factory=set)

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._accept, "127.0.0.1", 0)
        socket = self._server.sockets[0]
        return int(socket.getsockname()[1])

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for task in tuple(self._connections):
            task.cancel()
        if self._connections:
            await asyncio.gather(*self._connections, return_exceptions=True)

    def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(self._proxy_connection(reader, writer))
        self._connections.add(task)
        task.add_done_callback(self._connections.discard)

    async def _proxy_connection(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        server_reader, server_writer = await asyncio.open_connection(
            self.target_host,
            self.target_port,
        )

        async def client_to_server() -> None:
            buffer = bytearray()
            startup = True
            while data := await client_reader.read(64 * 1024):
                buffer.extend(data)
                while True:
                    if startup:
                        if len(buffer) < 4:
                            break
                        frame_length = int.from_bytes(buffer[:4], "big")
                        if frame_length < 8:
                            raise AssertionError(
                                "PostgreSQL proxy observed an invalid startup frame"
                            )
                        if len(buffer) < frame_length:
                            break
                        frame = bytes(buffer[:frame_length])
                        del buffer[:frame_length]
                        startup = False
                    else:
                        if len(buffer) < 5:
                            break
                        length = int.from_bytes(buffer[1:5], "big")
                        frame_length = 1 + length
                        if length < 4:
                            raise AssertionError(
                                "PostgreSQL proxy observed an invalid client frame"
                            )
                        if len(buffer) < frame_length:
                            break
                        frame = bytes(buffer[:frame_length])
                        del buffer[:frame_length]
                        if _is_commit_message(frame):
                            self.commit_seen.set()
                    server_writer.write(frame)
                    await server_writer.drain()

        async def server_to_client() -> None:
            buffer = bytearray()
            while data := await server_reader.read(64 * 1024):
                buffer.extend(data)
                while len(buffer) >= 5:
                    length = int.from_bytes(buffer[1:5], "big")
                    frame_length = 1 + length
                    if length < 4:
                        raise AssertionError("PostgreSQL proxy observed an invalid frame length")
                    if len(buffer) < frame_length:
                        break
                    frame = bytes(buffer[:frame_length])
                    del buffer[:frame_length]
                    if self.commit_seen.is_set():
                        if frame[:1] == b"Z":
                            self.acknowledgement_dropped.set()
                            client_writer.close()
                            await client_writer.wait_closed()
                            return
                        continue
                    client_writer.write(frame)
                    await client_writer.drain()

        client_task = asyncio.create_task(client_to_server())
        server_task = asyncio.create_task(server_to_client())
        try:
            _done, pending = await asyncio.wait(
                (client_task, server_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(client_task, server_task, return_exceptions=True)
        finally:
            server_writer.close()
            client_writer.close()
            await asyncio.gather(
                server_writer.wait_closed(),
                client_writer.wait_closed(),
                return_exceptions=True,
            )


def _is_commit_message(frame: bytes) -> bool:
    message_type = frame[:1]
    payload = frame[5:]
    if message_type == b"Q":
        query = payload.rstrip(b"\x00").strip().rstrip(b";").strip()
        return query.upper() == b"COMMIT"
    if message_type == b"P":
        _statement_name, separator, remainder = payload.partition(b"\x00")
        if not separator:
            return False
        query, separator, _parameter_types = remainder.partition(b"\x00")
        return bool(separator) and query.strip().rstrip(b";").strip().upper() == b"COMMIT"
    return False


def _route() -> RouteSpecification:
    return RouteSpecification(
        event_type="ambiguous.commit",
        route_key="ambiguous.commit",
        version=1,
        destination_kind="handler",
        destination_key="ambiguous.commit",
        required_scopes=(),
        authorization=AuthorizationMode.SNAPSHOT,
        service_policy=None,
        service_capabilities=None,
        maximum_snapshot_age_seconds=300,
        retry_policy=RetryPolicy(
            name="ambiguous.commit",
            base_delay_seconds=0,
            maximum_delay_seconds=0,
            handler_timeout_seconds=10,
            lease_duration_seconds=30,
        ),
    )


def _proxied_dsn(dsn: str, *, port: int) -> str:
    parsed = urlsplit(dsn)
    assert parsed.username is not None
    assert parsed.password is not None
    credentials = f"{quote(parsed.username, safe='')}:{quote(parsed.password, safe='')}"
    return urlunsplit(
        (
            parsed.scheme,
            f"{credentials}@127.0.0.1:{port}",
            parsed.path,
            parsed.query,
            "",
        )
    )


@asynccontextmanager
async def _drop_commit_acknowledgement(
    dsn: str,
) -> AsyncIterator[tuple[AsyncEngine, _CommitAcknowledgementDropProxy]]:
    parsed = urlsplit(dsn)
    assert parsed.hostname is not None
    assert parsed.port is not None
    proxy = _CommitAcknowledgementDropProxy(parsed.hostname, parsed.port)
    port = await proxy.start()
    engine = create_async_engine(
        sqlalchemy_async_dsn(_proxied_dsn(dsn, port=port)),
        connect_args={"ssl": False},
        poolclass=NullPool,
    )
    try:
        yield engine, proxy
    finally:
        await engine.dispose()
        await proxy.close()


async def _seed_direct(
    sessions: async_sessionmaker[AsyncSession],
    principal: Principal,
    *,
    dedupe_key: str,
) -> UUID:
    async with (
        sessions() as session,
        FastAPIEffectsUnitOfWork(
            session=session,
            principal=principal,
            store=PostgresStore(),
            routes=(_route(),),
        ) as uow,
    ):
        event = await uow.emit(
            Event(type="ambiguous.commit", version=1, data={"identity": dedupe_key}),
            dedupe_namespace="ambiguous-test",
            dedupe_key=dedupe_key,
        )
    return event.event_id


@pytest.mark.asyncio
async def test_application_commit_can_succeed_while_its_acknowledgement_is_lost(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    direct_sessions = async_sessionmaker(application, expire_on_commit=False)
    principal = Principal(tenant_id=uuid4(), subject_id="chaos:ambiguous-application")
    published_event_ids: list[UUID] = []
    try:
        await install_core_schema(migration, roles=roles)
        async with _drop_commit_acknowledgement(test_database.app_dsn) as (proxied, proxy):
            proxied_sessions = async_sessionmaker(proxied, expire_on_commit=False)

            async def publish() -> None:
                async with (
                    proxied_sessions() as session,
                    FastAPIEffectsUnitOfWork(
                        session=session,
                        principal=principal,
                        store=PostgresStore(),
                        routes=(_route(),),
                    ) as uow,
                ):
                    published = await uow.emit(
                        Event(
                            type="ambiguous.commit",
                            version=1,
                            data={"identity": "application"},
                        ),
                        dedupe_namespace="ambiguous-test",
                        dedupe_key="application",
                    )
                    published_event_ids.append(published.event_id)

            with pytest.raises(DBAPIError) as raised:
                await publish()
            await asyncio.wait_for(proxy.acknowledgement_dropped.wait(), timeout=2)

        assert len(published_event_ids) == 1, str(raised.value)
        published_event_id = published_event_ids[0]
        async with migration.connect() as connection:
            event_ids = tuple((await connection.scalars(select(EventRow.event_id))).all())
            delivery_count = await connection.scalar(select(func.count()).select_from(DeliveryRow))
        assert event_ids == (published_event_id,)
        assert delivery_count == 1

        retried_event_id = await _seed_direct(
            direct_sessions,
            principal,
            dedupe_key="application",
        )
        assert retried_event_id == published_event_id
        async with migration.connect() as connection:
            assert await connection.scalar(select(func.count()).select_from(EventRow)) == 1
            assert await connection.scalar(select(func.count()).select_from(DeliveryRow)) == 1
    finally:
        await application.dispose()
        await migration.dispose()


@pytest.mark.asyncio
async def test_claim_and_finalization_commits_remain_fenced_when_acknowledgements_are_lost(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay = create_async_engine(test_database.relay_sqlalchemy_dsn)
    app_sessions = async_sessionmaker(application, expire_on_commit=False)
    relay_sessions = async_sessionmaker(relay, expire_on_commit=False)
    migration_sessions = async_sessionmaker(migration, expire_on_commit=False)
    principal = Principal(tenant_id=uuid4(), subject_id="chaos:ambiguous-relay")
    leases = LeaseRepository()
    try:
        await install_core_schema(migration, roles=roles)
        event_id = await _seed_direct(app_sessions, principal, dedupe_key="relay")

        async with _drop_commit_acknowledgement(test_database.relay_dsn) as (proxied, proxy):
            proxied_sessions = async_sessionmaker(proxied, expire_on_commit=False)
            with pytest.raises(DBAPIError):
                async with proxied_sessions() as session:
                    await leases.claim(session, now=datetime.now(UTC))
            await asyncio.wait_for(proxy.acknowledgement_dropped.wait(), timeout=2)

        async with migration_sessions() as session:
            event_row = await session.scalar(select(EventRow).where(EventRow.event_id == event_id))
            delivery_row = await session.scalar(
                select(DeliveryRow).where(DeliveryRow.event_id == event_id)
            )
            assert delivery_row is not None
            attempt_row = await session.scalar(
                select(AttemptRow).where(AttemptRow.delivery_id == delivery_row.delivery_id)
            )
            assert event_row is not None
            assert attempt_row is not None
            stale = ClaimedDelivery(
                event=event_from_row(event_row),
                delivery=delivery_from_row(delivery_row),
                attempt=attempt_from_row(attempt_row),
                route_snapshot=dict(delivery_row.route_snapshot),
            )
        assert stale.delivery.state is DeliveryState.LEASED

        async with migration.begin() as connection:
            await connection.execute(
                update(DeliveryRow)
                .where(DeliveryRow.delivery_id == stale.delivery.delivery_id)
                .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        async with relay_sessions() as session:
            assert await leases.reconcile_expired(session, now=datetime.now(UTC)) == 1
        async with relay_sessions() as session:
            current = (await leases.claim(session, now=datetime.now(UTC)))[0]
        assert current.delivery.delivery_id == stale.delivery.delivery_id
        assert current.attempt.attempt_id != stale.attempt.attempt_id
        assert current.lease_token != stale.lease_token
        async with relay_sessions() as session:
            with pytest.raises(LeaseLost):
                await leases.succeed(session, stale, now=datetime.now(UTC))

        async with _drop_commit_acknowledgement(test_database.relay_dsn) as (proxied, proxy):
            proxied_sessions = async_sessionmaker(proxied, expire_on_commit=False)
            with pytest.raises(DBAPIError):
                async with proxied_sessions() as session:
                    await leases.succeed(session, current, now=datetime.now(UTC))
            await asyncio.wait_for(proxy.acknowledgement_dropped.wait(), timeout=2)

        async with migration.connect() as connection:
            final_state = await connection.scalar(
                select(DeliveryRow.state).where(
                    DeliveryRow.delivery_id == current.delivery.delivery_id
                )
            )
            attempts = [
                tuple(row)
                for row in (
                    await connection.execute(
                        select(AttemptRow.outcome, AttemptRow.failure_code)
                        .where(AttemptRow.delivery_id == current.delivery.delivery_id)
                        .order_by(AttemptRow.attempt_number)
                    )
                ).all()
            ]
        assert final_state == DeliveryState.SUCCEEDED.value
        assert attempts == [("abandoned", "lease.expired"), ("succeeded", None)]
        async with relay_sessions() as session:
            with pytest.raises(LeaseLost):
                await leases.succeed(session, current, now=datetime.now(UTC))
    finally:
        await relay.dispose()
        await application.dispose()
        await migration.dispose()

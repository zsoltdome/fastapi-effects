from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_effects import (
    AuthorizationMode,
    EffectContext,
    Event,
    FastAPIEffects,
    FastAPIEffectsUnitOfWork,
    PermanentDeliveryError,
    Principal,
    RetryableDeliveryError,
    RetryPolicy,
)
from fastapi_effects.core.context import current_principal
from fastapi_effects.core.delivery import DeliveryState
from fastapi_effects.core.routing import RouteSpecification
from fastapi_effects.handlers.dependencies import tenant_session_provider
from fastapi_effects.postgres import PollingRelay, PostgresStore
from fastapi_effects.postgres.leasing import ClaimedDelivery, LeaseRepository
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.sqlalchemy.models import AttemptRow, DeliveryRow
from tests.integration.postgres import ProvisionedDatabase, sqlalchemy_async_dsn

pytestmark = [pytest.mark.integration, pytest.mark.chaos]


class _SuccessSink:
    def __init__(self) -> None:
        self.deliveries: list[UUID] = []

    async def execute(self, claim: ClaimedDelivery) -> None:
        self.deliveries.append(claim.delivery.delivery_id)


class _TerminateBoundary(LeaseRepository):
    def __init__(self, admin: AsyncEngine, boundary: str) -> None:
        super().__init__()
        self._admin = admin
        self._boundary = boundary
        self.terminated = False

    async def _terminate(self, session: AsyncSession, boundary: str) -> None:
        if self.terminated or self._boundary != boundary:
            return
        backend_pid = int(await session.scalar(text("SELECT pg_backend_pid()")) or 0)
        async with self._admin.connect() as connection:
            terminated = await connection.scalar(
                text("SELECT pg_terminate_backend(:backend_pid)"),
                {"backend_pid": backend_pid},
            )
        assert terminated is True
        self.terminated = True

    async def reconcile_expired(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        batch_size: int = 100,
    ) -> int:
        await self._terminate(session, "reconcile")
        return await super().reconcile_expired(session, now=now, batch_size=batch_size)

    async def claim(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        batch_size: int = 50,
        per_tenant: int = 5,
    ) -> tuple[ClaimedDelivery, ...]:
        await self._terminate(session, "claim")
        return await super().claim(
            session,
            now=now,
            batch_size=batch_size,
            per_tenant=per_tenant,
        )

    async def succeed(
        self,
        session: AsyncSession,
        claim: ClaimedDelivery,
        *,
        now: datetime,
    ) -> None:
        await self._terminate(session, "success-finalization")
        await super().succeed(session, claim, now=now)

    async def fail(
        self,
        session: AsyncSession,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
        *,
        now: datetime,
        retry_after: timedelta | None = None,
    ) -> DeliveryState:
        await self._terminate(session, "failure-finalization")
        return await super().fail(
            session,
            claim,
            error,
            now=now,
            retry_after=retry_after,
        )


def _database_dsn(admin_dsn: str, database: str) -> str:
    parsed = urlsplit(admin_dsn)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", parsed.query, ""))


def _route(event_type: str = "control.boundary") -> RouteSpecification:
    return RouteSpecification(
        event_type=event_type,
        route_key="control.boundary",
        version=1,
        destination_kind="handler",
        destination_key="control.boundary",
        required_scopes=(),
        authorization=AuthorizationMode.SNAPSHOT,
        service_policy=None,
        service_capabilities=None,
        maximum_snapshot_age_seconds=300,
        retry_policy=RetryPolicy(
            name="control.boundary",
            base_delay_seconds=0,
            maximum_delay_seconds=0,
            handler_timeout_seconds=10,
            lease_duration_seconds=30,
        ),
    )


async def _seed(
    sessions: async_sessionmaker[AsyncSession],
    principal: Principal,
    *,
    route: RouteSpecification,
) -> UUID:
    async with (
        sessions() as session,
        FastAPIEffectsUnitOfWork(
            session=session,
            principal=principal,
            store=PostgresStore(),
            routes=(route,),
        ) as uow,
    ):
        event = await uow.emit(Event(type=route.event_type, version=1, data={"safe": True}))
    async with sessions() as session, session.begin():
        await session.execute(
            text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
            {"tenant": str(principal.tenant_id)},
        )
        delivery_id = await session.scalar(
            select(DeliveryRow.delivery_id).where(DeliveryRow.event_id == event.event_id)
        )
    assert delivery_id is not None
    return delivery_id


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["reconcile", "claim", "success-finalization"])
async def test_live_backend_loss_recovers_each_relay_control_boundary(
    test_database: ProvisionedDatabase,
    boundary: str,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn, pool_pre_ping=True)
    admin = create_async_engine(
        sqlalchemy_async_dsn(_database_dsn(test_database.admin_dsn, test_database.database)),
        pool_pre_ping=True,
    )
    app_sessions = async_sessionmaker(application, expire_on_commit=False)
    relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
    principal = Principal(tenant_id=uuid4(), subject_id=f"chaos:{boundary}")
    now = datetime.now(UTC)
    sink = _SuccessSink()
    try:
        await install_core_schema(migration, roles=roles)
        delivery_id = await _seed(app_sessions, principal, route=_route())
        fault = _TerminateBoundary(admin, boundary)
        faulted_relay = PollingRelay(
            sessions=relay_sessions,
            sink=sink,
            leases=fault,
        )
        started = asyncio.get_running_loop().time()
        if boundary in {"reconcile", "claim"}:
            with pytest.raises(DBAPIError):
                await faulted_relay.run_once()
        else:
            assert await faulted_relay.run_once() == 1
        assert fault.terminated
        assert asyncio.get_running_loop().time() - started < 2
        assert current_principal(required=False) is None

        async with migration.connect() as connection:
            state_after_fault = await connection.scalar(
                select(DeliveryRow.state).where(DeliveryRow.delivery_id == delivery_id)
            )
        if boundary == "success-finalization":
            assert state_after_fault == DeliveryState.LEASED.value
            async with migration.begin() as connection:
                await connection.execute(
                    update(DeliveryRow)
                    .where(DeliveryRow.delivery_id == delivery_id)
                    .values(lease_expires_at=now - timedelta(seconds=1))
                )
        else:
            assert state_after_fault == DeliveryState.PENDING.value

        recovered = PollingRelay(
            sessions=relay_sessions,
            sink=sink,
            leases=LeaseRepository(),
        )
        assert await recovered.run_once() == 1
        async with migration.connect() as connection:
            final_state = await connection.scalar(
                select(DeliveryRow.state).where(DeliveryRow.delivery_id == delivery_id)
            )
            attempts = [
                tuple(row)
                for row in (
                    await connection.execute(
                        select(AttemptRow.outcome, AttemptRow.failure_code)
                        .where(AttemptRow.delivery_id == delivery_id)
                        .order_by(AttemptRow.attempt_number)
                    )
                ).all()
            ]
        assert final_state == DeliveryState.SUCCEEDED.value
        if boundary == "success-finalization":
            assert attempts == [("abandoned", "lease.expired"), ("succeeded", None)]
            assert sink.deliveries == [delivery_id, delivery_id]
        else:
            assert attempts == [("succeeded", None)]
            assert sink.deliveries == [delivery_id]
    finally:
        await admin.dispose()
        await relay_engine.dispose()
        await application.dispose()
        await migration.dispose()


@pytest.mark.asyncio
async def test_live_application_session_loss_isolated_and_recovers_without_tenant_bleed(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn, pool_pre_ping=True)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn, pool_pre_ping=True)
    admin = create_async_engine(
        sqlalchemy_async_dsn(_database_dsn(test_database.admin_dsn, test_database.database)),
        pool_pre_ping=True,
    )
    app_sessions = async_sessionmaker(application, expire_on_commit=False)
    relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
    normal_provider = tenant_session_provider(app_sessions)
    provider_lock = asyncio.Lock()
    provider_faulted = False
    observed: list[tuple[UUID, str]] = []

    @asynccontextmanager
    async def faulting_provider(principal: Principal) -> AsyncIterator[AsyncSession]:
        nonlocal provider_faulted
        should_fault = False
        async with provider_lock:
            if not provider_faulted:
                provider_faulted = True
                should_fault = True
        if should_fault:
            async with app_sessions() as session:
                backend_pid = int(await session.scalar(text("SELECT pg_backend_pid()")) or 0)
                async with admin.connect() as connection:
                    terminated = await connection.scalar(
                        text("SELECT pg_terminate_backend(:backend_pid)"),
                        {"backend_pid": backend_pid},
                    )
                assert terminated is True
                await session.execute(text("SELECT 1"))
                yield session
        else:
            async with normal_provider(principal) as session:
                yield session

    async def principal_provider(request: object) -> Principal:
        del request
        raise AssertionError("HTTP principal provider is not used by the relay test")

    effects = FastAPIEffects(
        principal_provider=principal_provider,
        store=PostgresStore(),
        handler_session_provider=faulting_provider,
    )

    async def handler(context: EffectContext[object]) -> None:
        async with context.application_session() as session:
            tenant = await session.scalar(
                text("SELECT nullif(current_setting('fastapi_effects.tenant_id', true), '')")
            )
            subject = await session.scalar(
                text("SELECT nullif(current_setting('fastapi_effects.subject_id', true), '')")
            )
        assert str(tenant) == str(context.principal.tenant_id)
        assert subject == context.principal.subject_id
        observed.append((context.principal.tenant_id, context.principal.subject_id))

    effects.route(event_type="application.session", route_key="control.boundary").to_handler(
        handler,
        authorization=AuthorizationMode.SNAPSHOT,
        maximum_snapshot_age_seconds=300,
        retry_policy=_route("application.session").retry_policy,
    )
    effects.freeze()
    tenants = (
        Principal(tenant_id=uuid4(), subject_id="tenant-a:handler"),
        Principal(tenant_id=uuid4(), subject_id="tenant-b:handler"),
    )
    try:
        await install_core_schema(migration, roles=roles)
        delivery_ids = tuple(
            [
                await _seed(
                    app_sessions,
                    principal,
                    route=effects.routes[0],
                )
                for principal in tenants
            ]
        )
        first = PollingRelay(
            sessions=relay_sessions,
            sink=effects.handler_executor(),
            leases=LeaseRepository(),
        )
        assert await first.run_once() == 2
        assert provider_faulted
        assert len(observed) == 1
        assert current_principal(required=False) is None

        async with migration.connect() as connection:
            state_rows = (
                await connection.execute(
                    select(DeliveryRow.delivery_id, DeliveryRow.state).where(
                        DeliveryRow.delivery_id.in_(delivery_ids)
                    )
                )
            ).all()
            states: dict[UUID, str] = {row.delivery_id: row.state for row in state_rows}
        leased = [
            delivery_id
            for delivery_id, state in states.items()
            if state == DeliveryState.LEASED.value
        ]
        assert len(leased) == 1
        assert list(states.values()).count(DeliveryState.SUCCEEDED.value) == 1
        async with migration.begin() as connection:
            await connection.execute(
                update(DeliveryRow)
                .where(DeliveryRow.delivery_id == leased[0])
                .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )

        recovered = PollingRelay(
            sessions=relay_sessions,
            sink=effects.handler_executor(),
            leases=LeaseRepository(),
        )
        assert await recovered.run_once() == 1
        assert set(observed) == {(item.tenant_id, item.subject_id) for item in tenants}
        assert current_principal(required=False) is None
        async with migration.connect() as connection:
            final_states = tuple(
                (
                    await connection.scalars(
                        select(DeliveryRow.state).where(DeliveryRow.delivery_id.in_(delivery_ids))
                    )
                ).all()
            )
        assert final_states == (DeliveryState.SUCCEEDED.value, DeliveryState.SUCCEEDED.value)
    finally:
        await admin.dispose()
        await relay_engine.dispose()
        await application.dispose()
        await migration.dispose()

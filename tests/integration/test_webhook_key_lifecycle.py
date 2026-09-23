from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_effects import (
    Event,
    FastAPIEffectsConfigurationError,
    FastAPIEffectsUnitOfWork,
    PermanentDeliveryError,
    Principal,
    RetryableDeliveryError,
    RetryPolicy,
)
from fastapi_effects.core.delivery import DeliveryState
from fastapi_effects.postgres import PollingRelay, PostgresStore
from fastapi_effects.postgres.leasing import ClaimedDelivery, LeaseRepository
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.postgres.webhook_schema import install_webhook_schema
from fastapi_effects.sqlalchemy.models import AttemptRow, DeliveryRow
from fastapi_effects.webhooks.address_policy import EndpointTarget
from fastapi_effects.webhooks.http11 import HttpResponseMetadata
from fastapi_effects.webhooks.models import WebhookSecretVersionRow
from fastapi_effects.webhooks.secrets import (
    MasterKey,
    NoEligibleSigningKeyError,
    StaticMasterKeyProvider,
    WebhookSecretService,
)
from fastapi_effects.webhooks.sink import WebhookDeliverySink
from fastapi_effects.webhooks.subscriptions import SubscriptionRepository, WebhookRouteProvider
from fastapi_effects.webhooks.transport import TransportLimits, TransportResult
from tests.integration.postgres import ProvisionedDatabase, sqlalchemy_async_dsn

pytestmark = [pytest.mark.integration, pytest.mark.security, pytest.mark.chaos]


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class _LoopbackResolver:
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        del hostname, port
        return ("127.0.0.1",)


class _SuccessfulTransport:
    def __init__(self) -> None:
        self.limits = TransportLimits()
        self.message_ids: list[str] = []

    async def send(
        self,
        *,
        endpoint: EndpointTarget,
        connected_ip: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> TransportResult:
        del endpoint, body
        self.message_ids.append(headers["webhook-id"])
        return TransportResult(
            connected_ip=connected_ip,
            response=HttpResponseMetadata(
                status_code=202,
                headers={},
                discarded_body_bytes=0,
            ),
        )


class _TerminateFirstFailure(LeaseRepository):
    def __init__(self, admin: AsyncEngine) -> None:
        super().__init__()
        self._admin = admin
        self.terminated = False

    async def fail(
        self,
        session: AsyncSession,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
        *,
        now: datetime,
        retry_after: timedelta | None = None,
    ) -> DeliveryState:
        if not self.terminated:
            backend_pid = int(await session.scalar(text("SELECT pg_backend_pid()")) or 0)
            async with self._admin.connect() as connection:
                terminated = await connection.scalar(
                    text("SELECT pg_terminate_backend(:backend_pid)"),
                    {"backend_pid": backend_pid},
                )
            assert terminated is True
            self.terminated = True
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


async def _seed_webhook(
    sessions: async_sessionmaker[AsyncSession],
    *,
    service: WebhookSecretService,
    principal: Principal,
    event_type: str,
    at: datetime,
    rotate: bool,
) -> tuple[UUID, UUID]:
    async with (
        sessions() as session,
        FastAPIEffectsUnitOfWork(
            session=session,
            principal=principal,
            store=PostgresStore(),
            route_providers=(WebhookRouteProvider(),),
        ) as uow,
    ):
        created = await service.create(session, principal=principal, now=at)
        if rotate:
            await service.rotate(
                session,
                principal=principal,
                secret_set_id=created.secret_set_id,
                expected_revision=1,
                overlap=timedelta(seconds=1),
                now=at,
            )
        await SubscriptionRepository().create(
            session,
            principal=principal,
            exact_event_types=(event_type,),
            endpoint_url="https://receiver.example/hooks",
            retry_policy=RetryPolicy(
                name=f"lifecycle.{event_type.rsplit('.', 1)[-1]}",
                handler_timeout_seconds=10,
                lease_duration_seconds=30,
            ),
            secret_set_id=created.secret_set_id,
            now=at,
        )
        event = await uow.emit(Event(type=event_type, version=1, data={"safe": True}))
    async with sessions() as session, session.begin():
        await session.execute(
            text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
            {"tenant": str(principal.tenant_id)},
        )
        delivery_id = await session.scalar(
            select(DeliveryRow.delivery_id).where(DeliveryRow.event_id == event.event_id)
        )
    assert delivery_id is not None
    return created.secret_set_id, delivery_id


async def _revoke_active_key(
    sessions: async_sessionmaker[AsyncSession],
    *,
    service: WebhookSecretService,
    principal: Principal,
    secret_set_id: UUID,
    rotated: bool,
    at: datetime,
) -> None:
    async with (
        sessions() as session,
        FastAPIEffectsUnitOfWork(session=session, principal=principal),
    ):
        await service.revoke(
            session,
            principal=principal,
            secret_set_id=secret_set_id,
            version=2 if rotated else 1,
            expected_revision=2 if rotated else 1,
            now=at,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["revoked", "expired-retiring"])
async def test_two_tenant_key_lifecycle_survives_failed_terminal_finalization(
    test_database: ProvisionedDatabase,
    lifecycle: str,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay = create_async_engine(test_database.relay_sqlalchemy_dsn, pool_pre_ping=True)
    admin = create_async_engine(
        sqlalchemy_async_dsn(_database_dsn(test_database.admin_dsn, test_database.database)),
        pool_pre_ping=True,
    )
    app_sessions = async_sessionmaker(application, expire_on_commit=False)
    relay_sessions = async_sessionmaker(relay, expire_on_commit=False)
    provider = StaticMasterKeyProvider(
        keys=(MasterKey("lifecycle-master", b"k" * 32),),
        current_key_id="lifecycle-master",
    )
    service = WebhookSecretService(provider)
    tenant_a = Principal(tenant_id=uuid4(), subject_id="tenant-a:webhook-admin")
    tenant_b = Principal(tenant_id=uuid4(), subject_id="tenant-b:webhook-admin")
    seeded_at = datetime.now(UTC) - timedelta(seconds=5)
    clock = _Clock(datetime.now(UTC))
    rotated = lifecycle == "expired-retiring"
    transport = _SuccessfulTransport()
    try:
        await install_core_schema(migration, roles=roles)
        await install_webhook_schema(migration, roles=roles)
        secret_a, delivery_a = await _seed_webhook(
            app_sessions,
            service=service,
            principal=tenant_a,
            event_type=f"lifecycle.{lifecycle}",
            at=seeded_at,
            rotate=rotated,
        )
        secret_b, delivery_b = await _seed_webhook(
            app_sessions,
            service=service,
            principal=tenant_b,
            event_type=f"lifecycle.{lifecycle}.sibling",
            at=seeded_at,
            rotate=False,
        )

        async with relay_sessions() as session:
            eligible_before = await service.eligible_for_signing(
                session,
                tenant_id=tenant_a.tenant_id,
                secret_set_id=secret_a,
                now=seeded_at,
            )
        assert tuple(item.version for item in eligible_before) == ((2, 1) if rotated else (1,))

        await _revoke_active_key(
            app_sessions,
            service=service,
            principal=tenant_a,
            secret_set_id=secret_a,
            rotated=rotated,
            at=seeded_at,
        )
        async with relay_sessions() as session:
            with pytest.raises(NoEligibleSigningKeyError):
                await service.eligible_for_signing(
                    session,
                    tenant_id=tenant_a.tenant_id,
                    secret_set_id=secret_a,
                    now=clock.now(),
                )

        async with migration.connect() as connection:
            sibling_ciphertext = bytes(
                await connection.scalar(
                    select(WebhookSecretVersionRow.ciphertext).where(
                        WebhookSecretVersionRow.tenant_id == tenant_b.tenant_id,
                        WebhookSecretVersionRow.secret_set_id == secret_b,
                    )
                )
                or b""
            )
        sibling_digest = hashlib.sha256(sibling_ciphertext).digest()
        async with relay_sessions() as session:
            with pytest.raises(NoEligibleSigningKeyError):
                await service.eligible_for_signing(
                    session,
                    tenant_id=tenant_a.tenant_id,
                    secret_set_id=secret_b,
                    now=clock.now(),
                )
        async with migration.connect() as connection:
            unchanged_ciphertext = bytes(
                await connection.scalar(
                    select(WebhookSecretVersionRow.ciphertext).where(
                        WebhookSecretVersionRow.tenant_id == tenant_b.tenant_id,
                        WebhookSecretVersionRow.secret_set_id == secret_b,
                    )
                )
                or b""
            )
        assert hashlib.sha256(unchanged_ciphertext).digest() == sibling_digest

        missing_provider = WebhookSecretService(
            StaticMasterKeyProvider(
                keys=(MasterKey("different-master", b"m" * 32),),
                current_key_id="different-master",
            )
        )
        async with relay_sessions() as session:
            with pytest.raises(FastAPIEffectsConfigurationError, match="unavailable"):
                await missing_provider.eligible_for_signing(
                    session,
                    tenant_id=tenant_b.tenant_id,
                    secret_set_id=secret_b,
                    now=clock.now(),
                )

        sink = WebhookDeliverySink(
            sessions=relay_sessions,
            secrets=service,
            resolver=_LoopbackResolver(),
            transport=transport,  # type: ignore[arg-type]
            clock=clock,
            production=False,
        )
        interrupted_leases = _TerminateFirstFailure(admin)
        first_relay = PollingRelay(
            sessions=relay_sessions,
            sink=sink,
            leases=interrupted_leases,
            clock=clock,
        )
        assert await first_relay.run_once() == 2
        assert interrupted_leases.terminated

        async with migration.connect() as connection:
            states_after_interruption = dict(
                (
                    await connection.execute(
                        select(DeliveryRow.delivery_id, DeliveryRow.state).where(
                            DeliveryRow.delivery_id.in_((delivery_a, delivery_b))
                        )
                    )
                ).all()
            )
        assert states_after_interruption == {
            delivery_a: DeliveryState.LEASED.value,
            delivery_b: DeliveryState.SUCCEEDED.value,
        }

        async with migration.begin() as connection:
            await connection.execute(
                update(DeliveryRow)
                .where(DeliveryRow.delivery_id == delivery_a)
                .values(lease_expires_at=clock.now() - timedelta(seconds=1))
            )
        clock.value += timedelta(seconds=1)
        recovered_relay = PollingRelay(
            sessions=relay_sessions,
            sink=sink,
            leases=LeaseRepository(),
            clock=clock,
        )
        assert await recovered_relay.run_once() == 1

        async with migration.connect() as connection:
            rows = (
                await connection.execute(
                    select(
                        DeliveryRow.delivery_id,
                        DeliveryRow.tenant_id,
                        DeliveryRow.state,
                        DeliveryRow.route_snapshot,
                    ).where(DeliveryRow.delivery_id.in_((delivery_a, delivery_b)))
                )
            ).all()
            attempts_a = (
                await connection.execute(
                    select(AttemptRow.outcome, AttemptRow.failure_code)
                    .where(AttemptRow.delivery_id == delivery_a)
                    .order_by(AttemptRow.attempt_number)
                )
            ).all()
            attempts_b = (
                await connection.execute(
                    select(AttemptRow.outcome, AttemptRow.failure_code).where(
                        AttemptRow.delivery_id == delivery_b
                    )
                )
            ).all()
        by_delivery = {row.delivery_id: row for row in rows}
        assert by_delivery[delivery_a].tenant_id == tenant_a.tenant_id
        assert by_delivery[delivery_b].tenant_id == tenant_b.tenant_id
        assert by_delivery[delivery_a].state == DeliveryState.DEAD.value
        assert by_delivery[delivery_b].state == DeliveryState.SUCCEEDED.value
        destination_a = by_delivery[delivery_a].route_snapshot["destination"]
        assert destination_a["secret_set_id"] == str(secret_a)
        assert attempts_a == [
            ("abandoned", "lease.expired"),
            ("terminal", "webhook.no_eligible_signing_key"),
        ]
        assert attempts_b == [("succeeded", None)]
        assert len(transport.message_ids) == 1
    finally:
        await admin.dispose()
        await relay.dispose()
        await application.dispose()
        await migration.dispose()

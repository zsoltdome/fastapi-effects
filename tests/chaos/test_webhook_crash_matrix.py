from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_mergen import Event, MergenUnitOfWork, Principal, RetryPolicy
from fastapi_mergen.postgres import PostgresStore
from fastapi_mergen.postgres.leasing import LeaseRepository
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.postgres.webhook_schema import install_webhook_schema
from fastapi_mergen.sqlalchemy.models import DeliveryRow
from fastapi_mergen.webhooks.address_policy import EndpointTarget
from fastapi_mergen.webhooks.http11 import HttpResponseMetadata
from fastapi_mergen.webhooks.secrets import (
    MasterKey,
    StaticMasterKeyProvider,
    WebhookSecretService,
)
from fastapi_mergen.webhooks.sink import WebhookDeliverySink
from fastapi_mergen.webhooks.subscriptions import SubscriptionRepository, WebhookRouteProvider
from fastapi_mergen.webhooks.transport import TransportLimits, TransportResult
from tests.integration.postgres import ProvisionedDatabase

pytestmark = [pytest.mark.integration, pytest.mark.security]


class LoopbackResolver:
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        del hostname, port
        return ("127.0.0.1",)


class DeduplicatingReceiverTransport:
    def __init__(self) -> None:
        self.limits = TransportLimits()
        self.requests: list[tuple[bytes, dict[str, str]]] = []
        self.effective: set[str] = set()

    async def send(
        self,
        *,
        endpoint: EndpointTarget,
        connected_ip: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> TransportResult:
        del endpoint
        copied = dict(headers)
        self.requests.append((body, copied))
        self.effective.add(copied["webhook-id"])
        return TransportResult(
            connected_ip=connected_ip,
            response=HttpResponseMetadata(
                status_code=202,
                headers={},
                discarded_body_bytes=0,
            ),
        )


@pytest.mark.asyncio
async def test_receiver_success_then_relay_crash_retries_stable_identity(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    relay_engine = create_async_engine(test_database.relay_sqlalchemy_dsn)
    app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
    relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
    secrets = WebhookSecretService(
        StaticMasterKeyProvider(
            keys=(MasterKey("crash-mk", b"z" * 32),),
            current_key_id="crash-mk",
        )
    )
    receiver = DeduplicatingReceiverTransport()
    sink = WebhookDeliverySink(
        sessions=relay_sessions,
        secrets=secrets,
        resolver=LoopbackResolver(),
        transport=receiver,  # type: ignore[arg-type]
        production=False,
        allowed_ports=frozenset({443}),
    )
    leases = LeaseRepository()
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:crash")
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_webhook_schema(migration_engine, roles=roles)
        async with (
            app_sessions() as session,
            MergenUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                route_providers=(WebhookRouteProvider(),),
            ) as uow,
        ):
            secret = await secrets.create(session, principal=principal, now=datetime.now(UTC))
            await SubscriptionRepository().create(
                session,
                principal=principal,
                exact_event_types=("invoice.created",),
                endpoint_url="https://receiver.example/hooks",
                retry_policy=RetryPolicy(
                    name="crash",
                    handler_timeout_seconds=1,
                    lease_duration_seconds=2,
                ),
                secret_set_id=secret.secret_set_id,
                now=datetime.now(UTC),
            )
            await uow.emit(Event(type="invoice.created", version=1, data={"invoice": "1"}))

        first_time = datetime.now(UTC)
        async with relay_sessions() as session:
            first = (await leases.claim(session, now=first_time))[0]
        await sink.deliver_attempt(first)

        async with migration_engine.begin() as connection:
            await connection.execute(
                update(DeliveryRow)
                .where(DeliveryRow.delivery_id == first.delivery.delivery_id)
                .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
            )
        retry_time = datetime.now(UTC)
        async with relay_sessions() as session:
            assert await leases.reconcile_expired(session, now=retry_time) == 1
        async with relay_sessions() as session:
            second = (await leases.claim(session, now=retry_time))[0]
        await sink.deliver_attempt(second)
        async with relay_sessions() as session:
            await leases.succeed(session, second, now=retry_time)

        assert len(receiver.requests) == 2
        assert receiver.requests[0][0] == receiver.requests[1][0]
        assert receiver.requests[0][1]["webhook-id"] == receiver.requests[1][1]["webhook-id"]
        assert len(receiver.effective) == 1
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()

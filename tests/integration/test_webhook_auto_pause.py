from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_effects import Event, FastAPIEffectsUnitOfWork, Principal, RetryPolicy
from fastapi_effects.observability.events import RuntimeEvent
from fastapi_effects.postgres import PostgresStore
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.postgres.webhook_schema import install_webhook_schema
from fastapi_effects.sqlalchemy.models import DeliveryRow
from fastapi_effects.webhooks.models import WebhookAuditRow, WebhookSubscriptionRow
from fastapi_effects.webhooks.operations import WebhookHealthRepository
from fastapi_effects.webhooks.secrets import (
    MasterKey,
    StaticMasterKeyProvider,
    WebhookSecretService,
)
from fastapi_effects.webhooks.subscriptions import SubscriptionRepository, WebhookRouteProvider
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration


class RecordingEvents:
    def __init__(self) -> None:
        self.values: list[RuntimeEvent] = []

    def record(self, event: RuntimeEvent) -> None:
        self.values.append(event)


@pytest.mark.asyncio
async def test_failure_threshold_pauses_only_future_snapshotting(
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
    metrics = RecordingEvents()
    health = WebhookHealthRepository(relay_sessions, event_sink=metrics)
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:admin")
    secrets = WebhookSecretService(
        StaticMasterKeyProvider(
            keys=(MasterKey("mk", b"k" * 32),),
            current_key_id="mk",
        )
    )
    subscriptions = SubscriptionRepository()
    route_provider = WebhookRouteProvider()
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_webhook_schema(migration_engine, roles=roles)
        async with (
            app_sessions() as session,
            FastAPIEffectsUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                route_providers=(route_provider,),
            ) as uow,
        ):
            secret = await secrets.create(session, principal=principal, now=datetime.now(UTC))
            subscription = await subscriptions.create(
                session,
                principal=principal,
                exact_event_types=("invoice.created",),
                endpoint_url="https://health.example/hooks",
                retry_policy=RetryPolicy(name="health"),
                secret_set_id=secret.secret_set_id,
                auto_pause_threshold=2,
                now=datetime.now(UTC),
            )
            await uow.emit(Event(type="invoice.created", version=1, data={"n": 1}))

        await health.record_failure(
            tenant_id=tenant_id,
            subscription_id=subscription.subscription_id,
            now=datetime.now(UTC),
            status_class="http.500",
        )
        await health.record_failure(
            tenant_id=tenant_id,
            subscription_id=subscription.subscription_id,
            now=datetime.now(UTC),
            status_class="http.500",
        )

        async with (
            app_sessions() as session,
            FastAPIEffectsUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                route_providers=(route_provider,),
            ) as uow,
        ):
            await uow.emit(Event(type="invoice.created", version=1, data={"n": 2}))
        async with app_sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_id)},
            )
            delivery_count = await session.scalar(select(func.count()).select_from(DeliveryRow))
            audit_count = await session.scalar(
                select(func.count())
                .select_from(WebhookAuditRow)
                .where(WebhookAuditRow.action == "subscription.auto_paused")
            )
            row = await session.scalar(select(WebhookSubscriptionRow))
        assert delivery_count == 1
        assert audit_count == 1
        assert row is not None
        assert row.state == "paused"
        assert metrics.values[-1].attributes["auto_paused"] is True
        evidence = repr(metrics.values)
        assert "health.example" not in evidence
        assert secret.plaintext not in evidence
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()

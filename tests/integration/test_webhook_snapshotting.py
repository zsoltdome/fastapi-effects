from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_mergen import Event, MergenUnitOfWork, Principal, RetryPolicy
from fastapi_mergen.postgres import PostgresStore
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.postgres.webhook_schema import install_webhook_schema
from fastapi_mergen.sqlalchemy.models import DeliveryRow
from fastapi_mergen.webhooks.models import WebhookSecretVersionRow
from fastapi_mergen.webhooks.secrets import (
    MasterKey,
    StaticMasterKeyProvider,
    WebhookSecretService,
)
from fastapi_mergen.webhooks.subscriptions import (
    SubscriptionRepository,
    WebhookRouteProvider,
)
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_subscription_versions_and_secrets_snapshot_atomically(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
    provider = StaticMasterKeyProvider(
        keys=(MasterKey("mk-1", b"m" * 32),),
        current_key_id="mk-1",
    )
    secrets = WebhookSecretService(provider)
    subscriptions = SubscriptionRepository()
    route_provider = WebhookRouteProvider()
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:webhook-admin")
    policy = RetryPolicy(name="webhook.integration")
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_webhook_schema(migration_engine, roles=roles)

        async with app_sessions() as session:
            uow = MergenUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                route_providers=(route_provider,),
            )
            async with uow:
                created_secret = await secrets.create(
                    session,
                    principal=principal,
                    now=datetime.now(UTC),
                )
                subscription = await subscriptions.create(
                    session,
                    principal=principal,
                    exact_event_types=("invoice.created",),
                    endpoint_url="https://one.example/hooks",
                    retry_policy=policy,
                    secret_set_id=created_secret.secret_set_id,
                    now=datetime.now(UTC),
                )
                first_event = await uow.emit(
                    Event(type="invoice.created", version=1, data={"invoice_id": "inv-1"})
                )
            assert created_secret.plaintext not in repr(created_secret)

            second_uow = MergenUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                route_providers=(route_provider,),
            )
            async with second_uow:
                updated = await subscriptions.update(
                    session,
                    principal=principal,
                    subscription_id=subscription.subscription_id,
                    expected_revision=subscription.revision,
                    exact_event_types=("invoice.created",),
                    endpoint_url="https://two.example/hooks",
                    retry_policy=policy,
                    secret_set_id=created_secret.secret_set_id,
                    now=datetime.now(UTC),
                )
                second_event = await second_uow.emit(
                    Event(type="invoice.created", version=1, data={"invoice_id": "inv-2"})
                )
            assert updated.version == 2

            async with session.begin():
                await session.execute(
                    text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                    {"tenant": str(tenant_id)},
                )
                deliveries = (
                    await session.scalars(
                        select(DeliveryRow)
                        .where(
                            DeliveryRow.event_id.in_((first_event.event_id, second_event.event_id))
                        )
                        .order_by(DeliveryRow.created_at)
                    )
                ).all()
                encrypted = await session.scalar(select(WebhookSecretVersionRow))
            assert len(deliveries) == 2
            first_destination = deliveries[0].route_snapshot["destination"]
            second_destination = deliveries[1].route_snapshot["destination"]
            assert first_destination["endpoint_url"] == "https://one.example/hooks"
            assert first_destination["subscription_version"] == 1
            assert second_destination["endpoint_url"] == "https://two.example/hooks"
            assert second_destination["subscription_version"] == 2
            assert encrypted is not None
            assert created_secret.plaintext.encode() not in bytes(encrypted.ciphertext)

            async with session.begin():
                await session.execute(
                    text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                    {"tenant": str(tenant_id)},
                )
                rotated = await secrets.rotate(
                    session,
                    principal=principal,
                    secret_set_id=created_secret.secret_set_id,
                    expected_revision=1,
                    overlap=timedelta(minutes=5),
                    now=datetime.now(UTC),
                )
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
                    {"tenant": str(tenant_id)},
                )
                eligible = await secrets.eligible_for_signing(
                    session,
                    tenant_id=tenant_id,
                    secret_set_id=created_secret.secret_set_id,
                    now=datetime.now(UTC),
                )
            assert rotated.version == 2
            assert len(eligible) == 2
    finally:
        await app_engine.dispose()
        await migration_engine.dispose()

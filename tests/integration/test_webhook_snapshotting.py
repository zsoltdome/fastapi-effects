from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_effects import (
    AuthorizationDenied,
    Event,
    FastAPIEffectsConfigurationError,
    FastAPIEffectsUnitOfWork,
    Principal,
    RetryPolicy,
)
from fastapi_effects.postgres import PostgresStore
from fastapi_effects.postgres.leasing import LeaseRepository
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.postgres.webhook_schema import install_webhook_schema
from fastapi_effects.sqlalchemy.models import DeliveryRow
from fastapi_effects.webhooks.api import webhook_router
from fastapi_effects.webhooks.models import WebhookSecretVersionRow
from fastapi_effects.webhooks.operations import RetentionResult, WebhookOperations
from fastapi_effects.webhooks.secrets import (
    MasterKey,
    StaticMasterKeyProvider,
    WebhookSecretService,
)
from fastapi_effects.webhooks.subscriptions import (
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
            uow = FastAPIEffectsUnitOfWork(
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

            second_uow = FastAPIEffectsUnitOfWork(
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
                    text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
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
                    text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
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
                    text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
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


@pytest.mark.asyncio
async def test_webhook_replay_works_with_exact_application_role_grants(
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
    provider = StaticMasterKeyProvider(
        keys=(MasterKey("replay-key", b"r" * 32),),
        current_key_id="replay-key",
    )
    secrets = WebhookSecretService(provider)
    subscriptions = SubscriptionRepository()
    operations = WebhookOperations(subscriptions=subscriptions, secrets=secrets)
    tenant_id = uuid4()
    principal = Principal(
        tenant_id=tenant_id,
        subject_id="user:webhook-replay",
        scopes=frozenset({"webhooks:manage"}),
    )
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_webhook_schema(migration_engine, roles=roles)
        async with (
            app_sessions() as session,
            FastAPIEffectsUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                route_providers=(WebhookRouteProvider(),),
            ) as uow,
        ):
            created_secret = await secrets.create(
                session,
                principal=principal,
                now=datetime.now(UTC),
            )
            await subscriptions.create(
                session,
                principal=principal,
                exact_event_types=("invoice.replay",),
                endpoint_url="https://replay.example/hooks",
                retry_policy=RetryPolicy(name="webhook-replay"),
                secret_set_id=created_secret.secret_set_id,
                now=datetime.now(UTC),
            )
            await uow.emit(Event(type="invoice.replay", version=1, data={}))

        leases = LeaseRepository()
        async with relay_sessions() as session:
            original = (await leases.claim(session, now=datetime.now(UTC)))[0]
        async with relay_sessions() as session:
            await leases.succeed(session, original, now=datetime.now(UTC))

        async def retain_while_replay_is_open() -> RetentionResult:
            async with app_sessions() as retention_session:
                return await operations.retain(
                    retention_session,
                    principal=principal,
                    before=datetime.now(UTC) + timedelta(days=1),
                    batch_size=10,
                )

        async with (
            app_sessions() as session,
            FastAPIEffectsUnitOfWork(session=session, principal=principal),
        ):
            replay = await operations.replay(
                session,
                principal=principal,
                delivery_id=original.delivery.delivery_id,
                reason="manual.recovery",
                now=datetime.now(UTC),
            )
            retention_task = asyncio.create_task(retain_while_replay_is_open())
            await asyncio.sleep(0.05)
            retention_waited_for_replay = not retention_task.done()
        retention = await asyncio.wait_for(retention_task, timeout=1)
        assert retention_waited_for_replay
        assert retention.attempts == 1
        assert retention.deliveries == 0
        assert retention.events == 0
        assert replay.replay_of == original.delivery.delivery_id
        assert replay.destination_kind == "webhook"
        assert replay.state.value == "pending"

        current_principal = {"value": principal}

        async def session_dependency() -> AsyncIterator[AsyncSession]:
            async with app_sessions() as session:
                yield session

        async def principal_dependency() -> Principal:
            return current_principal["value"]

        app = FastAPI()
        app.include_router(
            webhook_router(
                session_dependency=session_dependency,
                principal_dependency=principal_dependency,
                operations=operations,
            )
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test.example",
        ) as client:
            response = await client.post(
                f"/webhooks/deliveries/{original.delivery.delivery_id}/replay",
                json={"reason": "manual.api-recovery"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["replay_of"] == str(original.delivery.delivery_id)

            current_principal["value"] = Principal(
                tenant_id=tenant_id,
                subject_id="user:without-management-scope",
            )
            with pytest.raises(AuthorizationDenied):
                await client.post(
                    f"/webhooks/deliveries/{original.delivery.delivery_id}/replay",
                    json={"reason": "manual.unauthorized"},
                )

        async with app_sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_id)},
            )
            original_state = await session.scalar(
                select(DeliveryRow.state).where(
                    DeliveryRow.delivery_id == original.delivery.delivery_id
                )
            )
            linked_replays = (
                await session.scalars(
                    select(DeliveryRow).where(
                        DeliveryRow.replay_of == original.delivery.delivery_id
                    )
                )
            ).all()
        assert original_state == "succeeded"
        assert len(linked_replays) == 2

        other = Principal(
            tenant_id=uuid4(),
            subject_id="user:other-tenant",
            scopes=frozenset({"webhooks:manage"}),
        )
        with pytest.raises(FastAPIEffectsConfigurationError, match="terminal delivery"):
            async with (
                app_sessions() as session,
                FastAPIEffectsUnitOfWork(session=session, principal=other),
            ):
                await operations.replay(
                    session,
                    principal=other,
                    delivery_id=original.delivery.delivery_id,
                    reason="manual.recovery",
                    now=datetime.now(UTC),
                )
    finally:
        await relay_engine.dispose()
        await app_engine.dispose()
        await migration_engine.dispose()

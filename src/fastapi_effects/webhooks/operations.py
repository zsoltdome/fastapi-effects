"""Tenant-safe webhook control operations, health accounting, and retention."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_effects.core.delivery import DeliveryRecord
from fastapi_effects.core.identity import UUIDSource
from fastapi_effects.core.principal import Principal
from fastapi_effects.core.protocols import UUIDGenerator
from fastapi_effects.errors import AuthorizationDenied, FastAPIEffectsConfigurationError
from fastapi_effects.observability import EventSink, NoOpEventSink, RuntimeEvent, RuntimeEventKind
from fastapi_effects.observability.protocols import record_safely
from fastapi_effects.postgres.leasing import LeaseRepository
from fastapi_effects.sqlalchemy.models import DeliveryRow
from fastapi_effects.sqlalchemy.repository import delivery_from_row
from fastapi_effects.webhooks.models import (
    WebhookAuditRow,
    WebhookSubscriptionRow,
)
from fastapi_effects.webhooks.secrets import CreatedWebhookSecret, WebhookSecretService
from fastapi_effects.webhooks.subscriptions import (
    SubscriptionRepository,
    SubscriptionState,
    WebhookSubscription,
)


class WebhookHealthObserver(Protocol):
    async def record_success(
        self, *, tenant_id: UUID, subscription_id: UUID, now: datetime
    ) -> None: ...

    async def record_failure(
        self,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        now: datetime,
        status_class: str,
    ) -> None: ...


@dataclass(slots=True)
class WebhookHealthRepository:
    sessions: async_sessionmaker[AsyncSession]
    event_sink: EventSink = field(default_factory=NoOpEventSink)
    uuid_source: UUIDGenerator = field(default_factory=UUIDSource)

    async def record_success(
        self, *, tenant_id: UUID, subscription_id: UUID, now: datetime
    ) -> None:
        async with self.sessions() as session, session.begin():
            row = await self._locked(session, tenant_id, subscription_id)
            if row.failure_streak:
                row.failure_streak = 0
                row.revision += 1
                row.updated_by = "relay:webhook"
                row.updated_at = now
        self._record_metric(now, "success", paused=False)

    async def record_failure(
        self,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        now: datetime,
        status_class: str,
    ) -> None:
        paused = False
        async with self.sessions() as session, session.begin():
            row = await self._locked(session, tenant_id, subscription_id)
            row.failure_streak += 1
            row.revision += 1
            row.updated_by = "relay:webhook"
            row.updated_at = now
            if (
                row.state == SubscriptionState.ACTIVE.value
                and row.failure_streak >= row.auto_pause_threshold
            ):
                row.state = SubscriptionState.PAUSED.value
                paused = True
                session.add(
                    WebhookAuditRow(
                        tenant_id=tenant_id,
                        audit_id=self.uuid_source.new_uuid(),
                        subject_id="relay:webhook",
                        action="subscription.auto_paused",
                        target_kind="subscription",
                        target_id=subscription_id,
                        details={"failure_streak": row.failure_streak},
                        occurred_at=now,
                    )
                )
        self._record_metric(now, status_class, paused=paused)

    async def _locked(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        subscription_id: UUID,
    ) -> WebhookSubscriptionRow:
        row = await session.scalar(
            select(WebhookSubscriptionRow)
            .where(
                WebhookSubscriptionRow.tenant_id == tenant_id,
                WebhookSubscriptionRow.subscription_id == subscription_id,
            )
            .with_for_update()
        )
        if row is None:
            raise FastAPIEffectsConfigurationError("Webhook health target no longer exists.")
        return row

    def _record_metric(self, now: datetime, outcome: str, *, paused: bool) -> None:
        self.event_sink.record(
            RuntimeEvent(
                kind=(
                    RuntimeEventKind.WEBHOOK_PAUSED
                    if paused
                    else RuntimeEventKind.WEBHOOK_ATTEMPTED
                ),
                occurred_at=now,
                attributes={
                    "destination.kind": "webhook",
                    "outcome": outcome[:64],
                    "auto_paused": paused,
                },
            )
        )


@dataclass(frozen=True, slots=True)
class RetentionResult:
    attempts: int
    deliveries: int
    events: int
    secret_versions: int


class WebhookOperations:
    def __init__(
        self,
        *,
        subscriptions: SubscriptionRepository,
        secrets: WebhookSecretService,
        leases: LeaseRepository | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self.subscriptions = subscriptions
        self.secrets = secrets
        self.leases = leases or LeaseRepository()
        self.event_sink = event_sink or NoOpEventSink()

    async def pause(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        subscription_id: UUID,
        expected_revision: int,
        now: datetime,
    ) -> WebhookSubscription:
        require_webhook_management(principal)
        return await self.subscriptions.set_state(
            session,
            principal=principal,
            subscription_id=subscription_id,
            expected_revision=expected_revision,
            state=SubscriptionState.PAUSED,
            now=now,
        )

    async def reactivate(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        subscription_id: UUID,
        expected_revision: int,
        now: datetime,
    ) -> WebhookSubscription:
        require_webhook_management(principal)
        return await self.subscriptions.set_state(
            session,
            principal=principal,
            subscription_id=subscription_id,
            expected_revision=expected_revision,
            state=SubscriptionState.ACTIVE,
            now=now,
        )

    async def rotate_secret(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        secret_set_id: UUID,
        expected_revision: int,
        overlap: timedelta,
        now: datetime,
    ) -> CreatedWebhookSecret:
        require_webhook_management(principal)
        return await self.secrets.rotate(
            session,
            principal=principal,
            secret_set_id=secret_set_id,
            expected_revision=expected_revision,
            overlap=overlap,
            now=now,
        )

    async def delivery(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        delivery_id: UUID,
    ) -> DeliveryRecord | None:
        require_webhook_management(principal)
        row = await session.scalar(
            select(DeliveryRow).where(
                DeliveryRow.tenant_id == principal.tenant_id,
                DeliveryRow.delivery_id == delivery_id,
                DeliveryRow.destination_kind == "webhook",
            )
        )
        return None if row is None else delivery_from_row(row)

    async def replay(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        delivery_id: UUID,
        reason: str,
        now: datetime,
    ) -> DeliveryRecord:
        require_webhook_management(principal)
        return await self.leases.replay_in_transaction(
            session,
            tenant_id=principal.tenant_id,
            delivery_id=delivery_id,
            actor=principal.subject_id,
            reason=reason,
            now=now,
            destination_kind="webhook",
        )

    async def retain(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        before: datetime,
        batch_size: int = 500,
    ) -> RetentionResult:
        require_webhook_management(principal)
        if session.in_transaction():
            raise FastAPIEffectsConfigurationError("Webhook retention requires an idle session.")
        if before.tzinfo is None or before.utcoffset() is None:
            raise FastAPIEffectsConfigurationError(
                "Webhook retention cutoff must be timezone-aware."
            )
        if not 1 <= batch_size <= 10_000:
            raise FastAPIEffectsConfigurationError("Webhook retention batch size is invalid.")
        async with session.begin():
            await session.execute(
                text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
                {"tenant": str(principal.tenant_id)},
            )
            await session.execute(
                text("SELECT set_config('fastapi_effects.subject_id', :subject, true)"),
                {"subject": principal.subject_id},
            )
            row = (
                await session.execute(
                    text(
                        "SELECT attempts_deleted, deliveries_deleted, events_deleted, "
                        "secret_versions_deleted FROM "
                        "fastapi_effects.prune_webhook_history(:tenant, :cutoff, :batch_size)"
                    ),
                    {
                        "tenant": principal.tenant_id,
                        "cutoff": before,
                        "batch_size": batch_size,
                    },
                )
            ).one()
        result = RetentionResult(
            attempts=int(row.attempts_deleted),
            deliveries=int(row.deliveries_deleted),
            events=int(row.events_deleted),
            secret_versions=int(row.secret_versions_deleted),
        )
        record_safely(
            self.event_sink,
            RuntimeEvent(
                kind=RuntimeEventKind.WEBHOOK_PRUNED,
                occurred_at=datetime.now(UTC),
                attributes={
                    "destination.kind": "webhook",
                    "pruned.count": (
                        result.attempts + result.deliveries + result.events + result.secret_versions
                    ),
                },
            ),
        )
        return result


def require_webhook_management(principal: Principal) -> None:
    if not ({"webhooks:manage", "fastapi_effects:operator"} & principal.scopes):
        raise AuthorizationDenied("Webhook operation requires management authority.")


__all__ = [
    "RetentionResult",
    "WebhookHealthObserver",
    "WebhookHealthRepository",
    "WebhookOperations",
    "require_webhook_management",
]

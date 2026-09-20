"""Versioned subscription repository and transactional route provider."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_effects.core.event import Event
from fastapi_effects.core.identity import UUIDSource
from fastapi_effects.core.policy import AuthorizationMode
from fastapi_effects.core.principal import Principal
from fastapi_effects.core.protocols import UUIDGenerator
from fastapi_effects.core.retry import RetryPolicy
from fastapi_effects.core.routing import RouteSpecification
from fastapi_effects.errors import FastAPIEffectsConfigurationError, OptimisticConflict
from fastapi_effects.webhooks.address_policy import parse_endpoint
from fastapi_effects.webhooks.models import (
    WebhookAuditRow,
    WebhookSecretSetRow,
    WebhookSubscriptionRow,
    WebhookSubscriptionVersionRow,
)

_EVENT_TYPE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class SubscriptionState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class WebhookSubscription:
    tenant_id: UUID
    subscription_id: UUID
    version: int
    revision: int
    exact_event_types: tuple[str, ...]
    endpoint_url: str
    state: SubscriptionState
    retry_policy: RetryPolicy
    secret_set_id: UUID
    failure_streak: int
    auto_pause_threshold: int
    created_at: datetime
    updated_at: datetime


class SubscriptionRepository:
    def __init__(self, *, uuid_source: UUIDGenerator | None = None) -> None:
        self._uuid_source = uuid_source or UUIDSource()

    async def create(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        exact_event_types: Iterable[str],
        endpoint_url: str,
        retry_policy: RetryPolicy,
        secret_set_id: UUID,
        now: datetime,
        auto_pause_threshold: int = 20,
    ) -> WebhookSubscription:
        event_types = _normalize_event_types(exact_event_types)
        endpoint = parse_endpoint(endpoint_url)
        _validate_threshold(auto_pause_threshold)
        secret_set = await session.scalar(
            select(WebhookSecretSetRow).where(
                WebhookSecretSetRow.tenant_id == principal.tenant_id,
                WebhookSecretSetRow.secret_set_id == secret_set_id,
            )
        )
        if secret_set is None:
            raise FastAPIEffectsConfigurationError("Webhook secret set does not exist.")
        subscription_id = self._uuid_source.new_uuid()
        head = WebhookSubscriptionRow(
            tenant_id=principal.tenant_id,
            subscription_id=subscription_id,
            current_version=1,
            revision=1,
            state=SubscriptionState.ACTIVE.value,
            failure_streak=0,
            auto_pause_threshold=auto_pause_threshold,
            created_by=principal.subject_id,
            updated_by=principal.subject_id,
            created_at=now,
            updated_at=now,
        )
        version = WebhookSubscriptionVersionRow(
            tenant_id=principal.tenant_id,
            subscription_id=subscription_id,
            version=1,
            exact_event_types=list(event_types),
            endpoint_url=endpoint.url,
            retry_policy=retry_policy.to_dict(),
            secret_set_id=secret_set_id,
            created_by=principal.subject_id,
            created_at=now,
        )
        session.add_all((head, version))
        await self._audit(
            session,
            principal=principal,
            action="subscription.created",
            target_id=subscription_id,
            now=now,
            details={"version": 1},
        )
        await session.flush()
        return _subscription(head, version)

    async def update(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        subscription_id: UUID,
        expected_revision: int,
        exact_event_types: Iterable[str],
        endpoint_url: str,
        retry_policy: RetryPolicy,
        secret_set_id: UUID,
        now: datetime,
    ) -> WebhookSubscription:
        head = await self._locked_head(session, principal.tenant_id, subscription_id)
        if head.revision != expected_revision:
            raise OptimisticConflict(resource="webhook_subscription")
        event_types = _normalize_event_types(exact_event_types)
        endpoint = parse_endpoint(endpoint_url)
        secret_set = await session.scalar(
            select(WebhookSecretSetRow).where(
                WebhookSecretSetRow.tenant_id == principal.tenant_id,
                WebhookSecretSetRow.secret_set_id == secret_set_id,
            )
        )
        if secret_set is None:
            raise FastAPIEffectsConfigurationError("Webhook secret set does not exist.")
        next_version = head.current_version + 1
        version = WebhookSubscriptionVersionRow(
            tenant_id=principal.tenant_id,
            subscription_id=subscription_id,
            version=next_version,
            exact_event_types=list(event_types),
            endpoint_url=endpoint.url,
            retry_policy=retry_policy.to_dict(),
            secret_set_id=secret_set_id,
            created_by=principal.subject_id,
            created_at=now,
        )
        session.add(version)
        head.current_version = next_version
        head.revision += 1
        head.updated_by = principal.subject_id
        head.updated_at = now
        await self._audit(
            session,
            principal=principal,
            action="subscription.updated",
            target_id=subscription_id,
            now=now,
            details={"version": next_version},
        )
        await session.flush()
        return _subscription(head, version)

    async def set_state(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        subscription_id: UUID,
        expected_revision: int,
        state: SubscriptionState,
        now: datetime,
        action: str | None = None,
    ) -> WebhookSubscription:
        if not isinstance(state, SubscriptionState):
            raise FastAPIEffectsConfigurationError("Webhook subscription state is invalid.")
        head = await self._locked_head(session, principal.tenant_id, subscription_id)
        if head.revision != expected_revision:
            raise OptimisticConflict(resource="webhook_subscription")
        head.state = state.value
        head.revision += 1
        head.updated_by = principal.subject_id
        head.updated_at = now
        version = await self._current_version(session, head)
        await self._audit(
            session,
            principal=principal,
            action=action or f"subscription.{state.value}",
            target_id=subscription_id,
            now=now,
            details={"revision": head.revision},
        )
        await session.flush()
        return _subscription(head, version)

    async def get(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
    ) -> WebhookSubscription | None:
        head = await session.scalar(
            select(WebhookSubscriptionRow).where(
                WebhookSubscriptionRow.tenant_id == tenant_id,
                WebhookSubscriptionRow.subscription_id == subscription_id,
            )
        )
        if head is None:
            return None
        return _subscription(head, await self._current_version(session, head))

    async def _locked_head(
        self, session: AsyncSession, tenant_id: UUID, subscription_id: UUID
    ) -> WebhookSubscriptionRow:
        head = await session.scalar(
            select(WebhookSubscriptionRow)
            .where(
                WebhookSubscriptionRow.tenant_id == tenant_id,
                WebhookSubscriptionRow.subscription_id == subscription_id,
            )
            .with_for_update()
        )
        if head is None:
            raise FastAPIEffectsConfigurationError("Webhook subscription does not exist.")
        return head

    async def _current_version(
        self, session: AsyncSession, head: WebhookSubscriptionRow
    ) -> WebhookSubscriptionVersionRow:
        version = await session.scalar(
            select(WebhookSubscriptionVersionRow).where(
                WebhookSubscriptionVersionRow.tenant_id == head.tenant_id,
                WebhookSubscriptionVersionRow.subscription_id == head.subscription_id,
                WebhookSubscriptionVersionRow.version == head.current_version,
            )
        )
        if version is None:
            raise FastAPIEffectsConfigurationError("Webhook subscription version is missing.")
        return version

    async def _audit(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        action: str,
        target_id: UUID,
        now: datetime,
        details: dict[str, object],
    ) -> None:
        session.add(
            WebhookAuditRow(
                tenant_id=principal.tenant_id,
                audit_id=self._uuid_source.new_uuid(),
                subject_id=principal.subject_id,
                action=action,
                target_kind="subscription",
                target_id=target_id,
                details=details,
                occurred_at=now,
            )
        )


class WebhookRouteProvider:
    """Snapshot active subscription versions in the caller-owned transaction."""

    async def routes_for(
        self,
        *,
        session: AsyncSession,
        principal: Principal,
        event: Event[object],
    ) -> Sequence[RouteSpecification]:
        rows = (
            await session.execute(
                select(WebhookSubscriptionRow, WebhookSubscriptionVersionRow)
                .join(
                    WebhookSubscriptionVersionRow,
                    (WebhookSubscriptionVersionRow.tenant_id == WebhookSubscriptionRow.tenant_id)
                    & (
                        WebhookSubscriptionVersionRow.subscription_id
                        == WebhookSubscriptionRow.subscription_id
                    )
                    & (
                        WebhookSubscriptionVersionRow.version
                        == WebhookSubscriptionRow.current_version
                    ),
                )
                .where(
                    WebhookSubscriptionRow.tenant_id == principal.tenant_id,
                    WebhookSubscriptionRow.state == SubscriptionState.ACTIVE.value,
                    WebhookSubscriptionVersionRow.exact_event_types.op("?")(event.type),
                )
                .order_by(WebhookSubscriptionRow.subscription_id)
            )
        ).all()
        routes: list[RouteSpecification] = []
        for head, version in rows:
            routes.append(
                RouteSpecification(
                    event_type=event.type,
                    route_key=f"webhook.{head.subscription_id.hex}",
                    version=version.version,
                    destination_kind="webhook",
                    destination_key=head.subscription_id.hex,
                    required_scopes=(),
                    authorization=AuthorizationMode.SNAPSHOT,
                    service_policy=None,
                    service_capabilities=None,
                    maximum_snapshot_age_seconds=315_360_000,
                    retry_policy=RetryPolicy.from_dict(dict(version.retry_policy)),
                    destination_metadata={
                        "subscription_id": str(head.subscription_id),
                        "subscription_version": version.version,
                        "endpoint_url": version.endpoint_url,
                        "secret_set_id": str(version.secret_set_id),
                    },
                )
            )
        return tuple(routes)


def _normalize_event_types(values: Iterable[str]) -> tuple[str, ...]:
    result = tuple(sorted(set(values)))
    if not result or len(result) > 64 or any(not _EVENT_TYPE.fullmatch(item) for item in result):
        raise FastAPIEffectsConfigurationError("Webhook exact event types are invalid.")
    return result


def _validate_threshold(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10_000:
        raise FastAPIEffectsConfigurationError("Webhook auto-pause threshold is invalid.")


def _subscription(
    head: WebhookSubscriptionRow,
    version: WebhookSubscriptionVersionRow,
) -> WebhookSubscription:
    return WebhookSubscription(
        tenant_id=head.tenant_id,
        subscription_id=head.subscription_id,
        version=version.version,
        revision=head.revision,
        exact_event_types=tuple(version.exact_event_types),
        endpoint_url=version.endpoint_url,
        state=SubscriptionState(head.state),
        retry_policy=RetryPolicy.from_dict(dict(version.retry_policy)),
        secret_set_id=version.secret_set_id,
        failure_streak=head.failure_streak,
        auto_pause_threshold=head.auto_pause_threshold,
        created_at=head.created_at,
        updated_at=head.updated_at,
    )


__all__ = [
    "SubscriptionRepository",
    "SubscriptionState",
    "WebhookRouteProvider",
    "WebhookSubscription",
]

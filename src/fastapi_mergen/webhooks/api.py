"""Optional FastAPI router for explicitly authorized webhook operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.protocols import Clock
from fastapi_mergen.core.retry import RetryPolicy
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.sqlalchemy.uow import MergenUnitOfWork
from fastapi_mergen.webhooks.operations import WebhookOperations, require_webhook_management
from fastapi_mergen.webhooks.subscriptions import WebhookSubscription


class RetryPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "webhook.default"
    version: int = 1
    max_attempts: int = 8
    maximum_elapsed_seconds: int = 86_400
    base_delay_seconds: float = 2.0
    maximum_delay_seconds: float = 900.0
    handler_timeout_seconds: float = 60.0
    lease_duration_seconds: float = 120.0
    jitter: str = "full"

    def to_domain(self) -> RetryPolicy:
        return RetryPolicy.from_dict(self.model_dump())


class CreateSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exact_event_types: list[str] = Field(min_length=1, max_length=64)
    endpoint_url: str = Field(min_length=1, max_length=2048)
    retry_policy: RetryPolicyInput = Field(default_factory=RetryPolicyInput)
    auto_pause_threshold: int = Field(default=20, ge=1, le=10_000)


class UpdateSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    exact_event_types: list[str] = Field(min_length=1, max_length=64)
    endpoint_url: str = Field(min_length=1, max_length=2048)
    retry_policy: RetryPolicyInput = Field(default_factory=RetryPolicyInput)
    secret_set_id: UUID


class StateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class RotateSecretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    overlap_seconds: int = Field(default=3600, ge=1, le=2_592_000)


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._-]*$")


class SubscriptionResponse(BaseModel):
    subscription_id: UUID
    version: int
    revision: int
    exact_event_types: tuple[str, ...]
    endpoint_url: str
    state: str
    secret_set_id: UUID
    failure_streak: int
    auto_pause_threshold: int


class CreatedSubscriptionResponse(SubscriptionResponse):
    signing_secret: str = Field(repr=False)


class RotatedSecretResponse(BaseModel):
    secret_set_id: UUID
    version: int
    signing_secret: str = Field(repr=False)


class ReplayResponse(BaseModel):
    delivery_id: UUID
    replay_of: UUID
    state: str


def webhook_router(
    *,
    session_dependency: Callable[..., Any],
    principal_dependency: Callable[..., Any],
    operations: WebhookOperations,
    clock: Clock | None = None,
) -> APIRouter:
    """Build a tenant-bound operations router without owning authentication."""
    router = APIRouter(prefix="/webhooks", tags=["webhooks"])
    runtime_clock = clock or SystemClock()

    @router.post("/subscriptions", response_model=CreatedSubscriptionResponse)
    async def create_subscription(
        body: CreateSubscriptionRequest,
        principal: Annotated[Principal, Depends(principal_dependency)],
        session: Annotated[AsyncSession, Depends(session_dependency)],
    ) -> CreatedSubscriptionResponse:
        require_webhook_management(principal)
        now = runtime_clock.now()
        async with MergenUnitOfWork(session=session, principal=principal):
            created_secret = await operations.secrets.create(
                session,
                principal=principal,
                now=now,
            )
            subscription = await operations.subscriptions.create(
                session,
                principal=principal,
                exact_event_types=body.exact_event_types,
                endpoint_url=body.endpoint_url,
                retry_policy=body.retry_policy.to_domain(),
                secret_set_id=created_secret.secret_set_id,
                now=now,
                auto_pause_threshold=body.auto_pause_threshold,
            )
        return CreatedSubscriptionResponse(
            **_subscription_values(subscription),
            signing_secret=created_secret.plaintext,
        )

    @router.put("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
    async def update_subscription(
        subscription_id: UUID,
        body: UpdateSubscriptionRequest,
        principal: Annotated[Principal, Depends(principal_dependency)],
        session: Annotated[AsyncSession, Depends(session_dependency)],
    ) -> SubscriptionResponse:
        require_webhook_management(principal)
        async with MergenUnitOfWork(session=session, principal=principal):
            value = await operations.subscriptions.update(
                session,
                principal=principal,
                subscription_id=subscription_id,
                expected_revision=body.expected_revision,
                exact_event_types=body.exact_event_types,
                endpoint_url=body.endpoint_url,
                retry_policy=body.retry_policy.to_domain(),
                secret_set_id=body.secret_set_id,
                now=runtime_clock.now(),
            )
        return SubscriptionResponse(**_subscription_values(value))

    @router.post(
        "/subscriptions/{subscription_id}/pause",
        response_model=SubscriptionResponse,
    )
    async def pause_subscription(
        subscription_id: UUID,
        body: StateRequest,
        principal: Annotated[Principal, Depends(principal_dependency)],
        session: Annotated[AsyncSession, Depends(session_dependency)],
    ) -> SubscriptionResponse:
        async with MergenUnitOfWork(session=session, principal=principal):
            value = await operations.pause(
                session,
                principal=principal,
                subscription_id=subscription_id,
                expected_revision=body.expected_revision,
                now=runtime_clock.now(),
            )
        return SubscriptionResponse(**_subscription_values(value))

    @router.post(
        "/subscriptions/{subscription_id}/reactivate",
        response_model=SubscriptionResponse,
    )
    async def reactivate_subscription(
        subscription_id: UUID,
        body: StateRequest,
        principal: Annotated[Principal, Depends(principal_dependency)],
        session: Annotated[AsyncSession, Depends(session_dependency)],
    ) -> SubscriptionResponse:
        async with MergenUnitOfWork(session=session, principal=principal):
            value = await operations.reactivate(
                session,
                principal=principal,
                subscription_id=subscription_id,
                expected_revision=body.expected_revision,
                now=runtime_clock.now(),
            )
        return SubscriptionResponse(**_subscription_values(value))

    @router.post("/secret-sets/{secret_set_id}/rotate", response_model=RotatedSecretResponse)
    async def rotate_secret(
        secret_set_id: UUID,
        body: RotateSecretRequest,
        principal: Annotated[Principal, Depends(principal_dependency)],
        session: Annotated[AsyncSession, Depends(session_dependency)],
    ) -> RotatedSecretResponse:
        async with MergenUnitOfWork(session=session, principal=principal):
            value = await operations.rotate_secret(
                session,
                principal=principal,
                secret_set_id=secret_set_id,
                expected_revision=body.expected_revision,
                overlap=timedelta(seconds=body.overlap_seconds),
                now=runtime_clock.now(),
            )
        return RotatedSecretResponse(
            secret_set_id=value.secret_set_id,
            version=value.version,
            signing_secret=value.plaintext,
        )

    @router.post("/deliveries/{delivery_id}/replay", response_model=ReplayResponse)
    async def replay_delivery(
        delivery_id: UUID,
        body: ReplayRequest,
        principal: Annotated[Principal, Depends(principal_dependency)],
        session: Annotated[AsyncSession, Depends(session_dependency)],
    ) -> ReplayResponse:
        async with MergenUnitOfWork(session=session, principal=principal):
            value = await operations.replay(
                session,
                principal=principal,
                delivery_id=delivery_id,
                reason=body.reason,
                now=runtime_clock.now(),
            )
        if value.replay_of is None:
            raise HTTPException(status_code=500, detail="Replay linkage was not persisted.")
        return ReplayResponse(
            delivery_id=value.delivery_id,
            replay_of=value.replay_of,
            state=value.state.value,
        )

    return router


def _subscription_values(value: WebhookSubscription) -> dict[str, Any]:
    return {
        "subscription_id": value.subscription_id,
        "version": value.version,
        "revision": value.revision,
        "exact_event_types": value.exact_event_types,
        "endpoint_url": value.endpoint_url,
        "state": value.state.value,
        "secret_set_id": value.secret_set_id,
        "failure_streak": value.failure_streak,
        "auto_pause_threshold": value.auto_pause_threshold,
    }


__all__ = [
    "CreateSubscriptionRequest",
    "CreatedSubscriptionResponse",
    "RetryPolicyInput",
    "SubscriptionResponse",
    "UpdateSubscriptionRequest",
    "webhook_router",
]

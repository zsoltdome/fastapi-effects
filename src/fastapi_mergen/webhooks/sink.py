"""Signed webhook sink executed only after delivery claim locks are released."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_mergen.core.protocols import Clock
from fastapi_mergen.core.retry import RetryPolicy
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.errors import (
    MergenConfigurationError,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_mergen.postgres.leasing import ClaimedDelivery
from fastapi_mergen.webhooks.classification import (
    ResponseDisposition,
    classify_response,
)
from fastapi_mergen.webhooks.operations import WebhookHealthObserver
from fastapi_mergen.webhooks.secrets import WebhookSecretService
from fastapi_mergen.webhooks.serializer import (
    serialize_webhook_envelope,
    webhook_message_id,
)
from fastapi_mergen.webhooks.signing import sign_webhook
from fastapi_mergen.webhooks.transport import (
    AddressResolver,
    ExplicitIPTransport,
    SystemAddressResolver,
    resolve_endpoint,
)


@dataclass(frozen=True, slots=True)
class WebhookAttemptResult:
    message_id: str
    request_body_digest: str
    signed_body_digest: str
    signature_count: int
    connected_ip: str
    status_code: int
    response_body_persisted: bool = False


@dataclass(slots=True)
class WebhookDeliverySink:
    sessions: async_sessionmaker[AsyncSession]
    secrets: WebhookSecretService
    resolver: AddressResolver = field(default_factory=SystemAddressResolver)
    transport: ExplicitIPTransport = field(default_factory=ExplicitIPTransport)
    clock: Clock = field(default_factory=SystemClock)
    production: bool = True
    allowed_ports: frozenset[int] = frozenset({443})
    health: WebhookHealthObserver | None = None

    async def execute(self, claim: ClaimedDelivery) -> None:
        subscription_id = _required_uuid(_destination(claim.route_snapshot), "subscription_id")
        try:
            result = await self.deliver_attempt(claim)
        except (RetryableDeliveryError, PermanentDeliveryError) as exc:
            if self.health is not None:
                await self.health.record_failure(
                    tenant_id=claim.delivery.tenant_id,
                    subscription_id=subscription_id,
                    now=self.clock.now(),
                    status_class=exc.code[:64],
                )
            raise
        else:
            if self.health is not None:
                await self.health.record_success(
                    tenant_id=claim.delivery.tenant_id,
                    subscription_id=subscription_id,
                    now=self.clock.now(),
                )
            del result

    async def deliver_attempt(self, claim: ClaimedDelivery) -> WebhookAttemptResult:
        if claim.delivery.destination_kind != "webhook":
            raise PermanentDeliveryError(
                code="webhook.destination_mismatch",
                summary="Webhook sink received another destination kind.",
            )
        destination = _destination(claim.route_snapshot)
        endpoint_url = _required_string(destination, "endpoint_url")
        secret_set_id = _required_uuid(destination, "secret_set_id")
        now = self.clock.now()
        async with self.sessions() as session:
            signing_secrets = await self.secrets.eligible_for_signing(
                session,
                tenant_id=claim.delivery.tenant_id,
                secret_set_id=secret_set_id,
                now=now,
            )
        body = serialize_webhook_envelope(
            delivery_id=claim.delivery.delivery_id,
            event=claim.event,
        )
        message_id = webhook_message_id(claim.delivery.delivery_id)
        signed = sign_webhook(
            message_id=message_id,
            timestamp=now,
            body=body,
            secrets=(item.material for item in signing_secrets),
        )
        endpoint, addresses = await resolve_endpoint(
            endpoint_url,
            resolver=self.resolver,
            production=self.production,
            allowed_ports=self.allowed_ports,
        )
        last_error: RetryableDeliveryError | None = None
        transport_result = None
        for address in addresses:
            try:
                transport_result = await self.transport.send(
                    endpoint=endpoint,
                    connected_ip=address,
                    body=body,
                    headers=signed.values,
                )
                break
            except RetryableDeliveryError as exc:
                last_error = exc
        if transport_result is None:
            if last_error is not None:
                raise last_error
            raise RetryableDeliveryError(
                code="webhook.transport_failed",
                summary="Webhook endpoint had no connectable approved address.",
            )
        policy = RetryPolicy.from_dict(dict(claim.route_snapshot["retry"]))
        response = transport_result.response
        classification = classify_response(
            response.status_code,
            response.headers,
            now=now,
            maximum_retry_after=timedelta(seconds=policy.maximum_delay_seconds),
            deadline=claim.delivery.created_at + timedelta(seconds=policy.maximum_elapsed_seconds),
        )
        if classification.disposition is ResponseDisposition.RETRYABLE:
            raise RetryableDeliveryError(
                code=classification.code,
                summary="Webhook receiver requested or requires a retry.",
                retry_after=classification.retry_after,
            )
        if classification.disposition is ResponseDisposition.PERMANENT:
            raise PermanentDeliveryError(
                code=classification.code,
                summary="Webhook receiver returned a terminal response.",
            )
        digest = hashlib.sha256(body).hexdigest()
        return WebhookAttemptResult(
            message_id=message_id,
            request_body_digest=digest,
            signed_body_digest=digest,
            signature_count=signed.signature_count,
            connected_ip=transport_result.connected_ip,
            status_code=response.status_code,
        )


def _destination(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = snapshot.get("destination")
    if not isinstance(value, dict):
        raise MergenConfigurationError("Webhook destination snapshot is invalid.")
    return value


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise MergenConfigurationError("Webhook destination snapshot is invalid.")
    return result


def _required_uuid(value: dict[str, Any], key: str) -> UUID:
    try:
        return UUID(_required_string(value, key))
    except ValueError as exc:
        raise MergenConfigurationError("Webhook destination snapshot is invalid.") from exc


__all__ = ["WebhookAttemptResult", "WebhookDeliverySink"]

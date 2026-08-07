"""Conformance adapter for the real PostgreSQL and webhook implementation paths."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_mergen.conformance.contract import Capability, Invariant
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.protocols import (
    ConformanceAccessDenied,
    WebhookAttemptView,
)
from fastapi_mergen.errors import PermanentDeliveryError
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.testing.postgres_driver import PostgresBoundaryDriver
from fastapi_mergen.webhooks.address_policy import parse_endpoint, validate_public_addresses
from fastapi_mergen.webhooks.signing import sign_webhook, verify_webhook


class PostgresWebhookBoundaryDriver(PostgresBoundaryDriver):
    """Exercise PostgreSQL identity plus production signing/address-policy code."""

    def __init__(
        self,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> None:
        super().__init__(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        self._webhook_secret = hashlib.sha256(b"mergen-conformance-webhook-key").digest()
        self._webhook_attempts = 0

    @classmethod
    async def create(
        cls,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> PostgresWebhookBoundaryDriver:
        driver = cls(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        await driver._prepare_business_table()
        return driver

    @property
    def manifest(self) -> CapabilityManifest:
        core = super().manifest
        return CapabilityManifest(
            adapter_name="fastapi-mergen-postgresql-webhooks",
            adapter_version="0.8.0b1",
            implementation=("fastapi_mergen.testing.webhook_driver.PostgresWebhookBoundaryDriver"),
            capabilities=core.capabilities | {Capability.WEBHOOKS},
            invariants=core.invariants | {Invariant.WEBHOOK_BOUNDARY},
            metadata={"driver": "asyncpg", "store": "postgresql", "transport": "http11"},
        )

    async def reset(self) -> None:
        await super().reset()
        self._webhook_attempts = 0

    async def public_evidence(self) -> dict[str, int]:
        evidence = await super().public_evidence()
        evidence["webhook_attempts"] = self._webhook_attempts
        return evidence

    async def deliver_webhook(
        self,
        *,
        message_id: str,
        body: bytes,
        endpoint_url: str,
        resolved_addresses: Sequence[str],
        attempt_no: int,
    ) -> WebhookAttemptView:
        parse_endpoint(endpoint_url)
        try:
            addresses = validate_public_addresses(list(resolved_addresses))
        except PermanentDeliveryError as exc:
            raise ConformanceAccessDenied from exc
        timestamp = datetime.now(UTC)
        signed = sign_webhook(
            message_id=message_id,
            timestamp=timestamp,
            body=body,
            secrets=(self._webhook_secret,),
        )
        if not verify_webhook(secret=self._webhook_secret, body=body, headers=signed.values):
            raise AssertionError("Production webhook signature failed receiver verification.")
        self._webhook_attempts += 1
        digest = hashlib.sha256(body).hexdigest()
        return WebhookAttemptView(
            message_id=message_id,
            attempt_no=attempt_no,
            request_body_digest=digest,
            signed_body_digest=digest,
            signature_count=signed.signature_count,
            connected_ip=addresses[0],
            status_code=202,
            response_body_persisted=False,
        )


__all__ = ["PostgresWebhookBoundaryDriver"]

"""Cumulative real-runtime adapter for the complete Boundary Contract profile."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_mergen import __version__
from fastapi_mergen.conformance.contract import Capability, Invariant
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.protocols import (
    CommandResult,
    DelegationView,
    ExecutorHandoffView,
    WebhookAttemptView,
)
from fastapi_mergen.conformance.safety import JsonValue
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.testing.delegation_driver import RealDelegationBoundaryDriver
from fastapi_mergen.testing.evidence import postgres_evidence_metadata
from fastapi_mergen.testing.idempotency_driver import PostgresIdempotencyBoundaryDriver
from fastapi_mergen.testing.postgres_driver import PostgresBoundaryDriver
from fastapi_mergen.testing.taskiq_driver import PostgresTaskiqBoundaryDriver
from fastapi_mergen.testing.webhook_driver import PostgresWebhookBoundaryDriver


class PostgresCompleteBoundaryDriver(PostgresBoundaryDriver):
    """Combine every production-backed facet under one cumulative manifest."""

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
        self._commands: PostgresIdempotencyBoundaryDriver | None = None
        self._webhooks: PostgresWebhookBoundaryDriver | None = None
        self._taskiq: PostgresTaskiqBoundaryDriver | None = None
        self._delegation = RealDelegationBoundaryDriver()

    @classmethod
    async def create(
        cls,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
        redis_url: str | None = None,
    ) -> PostgresCompleteBoundaryDriver:
        driver = cls(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        await driver._prepare_business_table()
        driver._manifest_metadata = await postgres_evidence_metadata(migration_engine)
        driver._commands = await PostgresIdempotencyBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        driver._webhooks = await PostgresWebhookBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        driver._taskiq = await PostgresTaskiqBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
            redis_url=redis_url,
        )
        return driver

    @property
    def manifest(self) -> CapabilityManifest:
        metadata: dict[str, JsonValue] = dict(self._manifest_metadata)
        metadata.update(
            {
                "certification.scope": "cumulative-real-runtime",
                "webhook.transport": "explicit-ip-tls-http11",
                "executor.broker": "taskiq-redis-streams",
                "executor.worker_boundary": "subprocess",
                "command.locking": "postgresql-advisory",
                "delegation.bridge": "target-bound",
            }
        )
        return CapabilityManifest(
            adapter_name="fastapi-mergen-postgresql-complete",
            adapter_version=__version__,
            implementation="fastapi_mergen.testing.complete_driver.PostgresCompleteBoundaryDriver",
            capabilities=frozenset(Capability),
            invariants=frozenset(Invariant),
            metadata=metadata,
        )

    async def reset(self) -> None:
        await super().reset()
        await self._required_commands().reset()
        await self._required_webhooks().reset()
        await self._required_taskiq().reset()
        await self._delegation.reset()

    async def close(self) -> None:
        taskiq, self._taskiq = self._taskiq, None
        webhooks, self._webhooks = self._webhooks, None
        commands, self._commands = self._commands, None
        if taskiq is not None:
            await taskiq.close()
        if webhooks is not None:
            await webhooks.close()
        if commands is not None:
            await commands.close()
        await self._delegation.close()
        await super().close()

    async def public_evidence(self) -> dict[str, int]:
        evidence = await super().public_evidence()
        for feature in (
            self._required_commands(),
            self._required_webhooks(),
            self._required_taskiq(),
            self._delegation,
        ):
            evidence.update(await feature.public_evidence())
        return evidence

    async def execute_command(
        self,
        *,
        principal: Principal,
        route_id: str,
        method: str,
        idempotency_key: str,
        request_fingerprint: str,
        operation: Callable[[], Awaitable[str]],
    ) -> CommandResult:
        return await self._required_commands().execute_command(
            principal=principal,
            route_id=route_id,
            method=method,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            operation=operation,
        )

    async def deliver_webhook(
        self,
        *,
        message_id: str,
        body: bytes,
        endpoint_url: str,
        resolved_addresses: Sequence[str],
        attempt_no: int,
    ) -> WebhookAttemptView:
        return await self._required_webhooks().deliver_webhook(
            message_id=message_id,
            body=body,
            endpoint_url=endpoint_url,
            resolved_addresses=resolved_addresses,
            attempt_no=attempt_no,
        )

    async def enqueue_handoff(
        self,
        *,
        principal: Principal,
        delivery_id: UUID,
        attempt_id: UUID,
    ) -> ExecutorHandoffView:
        return await self._required_taskiq().enqueue_handoff(
            principal=principal,
            delivery_id=delivery_id,
            attempt_id=attempt_id,
        )

    async def execute_handoff(
        self,
        *,
        handoff_id: UUID,
        worker_id: str,
    ) -> ExecutorHandoffView:
        return await self._required_taskiq().execute_handoff(
            handoff_id=handoff_id,
            worker_id=worker_id,
        )

    async def mint_delegation(
        self,
        *,
        principal: Principal,
        audience: str,
        method: str,
        path: str,
        scopes: frozenset[str],
        ttl: timedelta,
    ) -> str:
        return await self._delegation.mint_delegation(
            principal=principal,
            audience=audience,
            method=method,
            path=path,
            scopes=scopes,
            ttl=ttl,
        )

    async def verify_delegation(
        self,
        *,
        token: str,
        audience: str,
        method: str,
        path: str,
        required_scopes: frozenset[str],
    ) -> DelegationView:
        return await self._delegation.verify_delegation(
            token=token,
            audience=audience,
            method=method,
            path=path,
            required_scopes=required_scopes,
        )

    def _required_commands(self) -> PostgresIdempotencyBoundaryDriver:
        if self._commands is None:
            raise RuntimeError("Complete command facet is closed.")
        return self._commands

    def _required_webhooks(self) -> PostgresWebhookBoundaryDriver:
        if self._webhooks is None:
            raise RuntimeError("Complete webhook facet is closed.")
        return self._webhooks

    def _required_taskiq(self) -> PostgresTaskiqBoundaryDriver:
        if self._taskiq is None:
            raise RuntimeError("Complete Taskiq facet is closed.")
        return self._taskiq


__all__ = ["PostgresCompleteBoundaryDriver"]

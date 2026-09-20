"""Real PostgreSQL adapter for transactional command-idempotency conformance."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_effects import __version__
from fastapi_effects.conformance.contract import Capability, Invariant
from fastapi_effects.conformance.manifest import CapabilityManifest
from fastapi_effects.conformance.protocols import CommandResult, ConformanceConflict
from fastapi_effects.core.principal import Principal
from fastapi_effects.errors import CommandConflict
from fastapi_effects.idempotency.command import CommandContext
from fastapi_effects.idempotency.fingerprint import RequestFingerprint
from fastapi_effects.idempotency.models import CommandIdentity
from fastapi_effects.idempotency.responses import CapturedResponse
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.sqlalchemy.models import SCHEMA
from fastapi_effects.testing.evidence import postgres_evidence_metadata
from fastapi_effects.testing.postgres_driver import PostgresBoundaryDriver


class PostgresIdempotencyBoundaryDriver(PostgresBoundaryDriver):
    """Exercise command transactions through application-role PostgreSQL sessions."""

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
        self._command_executions = 0
        self._command_replays = 0

    @classmethod
    async def create(
        cls,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> PostgresIdempotencyBoundaryDriver:
        driver = cls(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        await driver._prepare_business_table()
        driver._manifest_metadata = await postgres_evidence_metadata(migration_engine)
        return driver

    @property
    def manifest(self) -> CapabilityManifest:
        core = super().manifest
        return CapabilityManifest(
            adapter_name="fastapi_effects_postgresql-commands",
            adapter_version=__version__,
            implementation=(
                "fastapi_effects.testing.idempotency_driver.PostgresIdempotencyBoundaryDriver"
            ),
            capabilities=core.capabilities | {Capability.COMMAND_IDEMPOTENCY},
            invariants=core.invariants | {Invariant.COMMAND_IDENTITY},
            metadata={**core.metadata, "command.locking": "postgresql-advisory"},
        )

    async def reset(self) -> None:
        await super().reset()
        async with self._migration_engine.begin() as connection:
            await connection.execute(text(f"DELETE FROM {SCHEMA}.commands"))
        self._command_executions = 0
        self._command_replays = 0

    async def public_evidence(self) -> dict[str, int]:
        evidence = await super().public_evidence()
        evidence.update(
            command_executions=self._command_executions,
            command_replays=self._command_replays,
        )
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
        identity = CommandIdentity.from_key(
            tenant_id=principal.tenant_id,
            route_id=route_id,
            method=method,
            key=idempotency_key,
        )
        fingerprint = RequestFingerprint.from_hex(request_fingerprint)
        try:
            async with self._app_sessions() as session:
                context = CommandContext(
                    session=session,
                    principal=principal,
                    identity=identity,
                    fingerprint=fingerprint,
                )
                async with context:
                    generation = context.generation
                    if context.replayed:
                        response = context.response
                        if response is None:
                            raise RuntimeError("Replayed command has no captured response.")
                        digest = response.body.decode("ascii")
                        self._command_replays += 1
                        return CommandResult(
                            executed=False,
                            replayed=True,
                            response_digest=digest,
                            generation=generation,
                        )
                    digest = await operation()
                    await context.complete(
                        CapturedResponse(
                            status_code=200,
                            media_type="text/plain",
                            body=digest.encode("ascii"),
                        )
                    )
                    self._command_executions += 1
                    return CommandResult(
                        executed=True,
                        replayed=False,
                        response_digest=digest,
                        generation=generation,
                    )
        except CommandConflict as exc:
            raise ConformanceConflict from exc


__all__ = ["PostgresIdempotencyBoundaryDriver"]

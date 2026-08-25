"""Boundary Contract adapter that exercises the real PostgreSQL core runtime."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fastapi_mergen import __version__
from fastapi_mergen.api import EffectContext
from fastapi_mergen.conformance.contract import Capability, Invariant
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.protocols import (
    AuthorityView,
    BoundarySnapshot,
    ConformanceAccessDenied,
    ConformanceLeaseLost,
    DelegationView,
    DeliveryView,
    LeaseView,
    PublishedEvent,
)
from fastapi_mergen.conformance.safety import JsonValue
from fastapi_mergen.core.context import current_principal, principal_context
from fastapi_mergen.core.delivery import DeliveryRecord
from fastapi_mergen.core.event import Event
from fastapi_mergen.core.policy import AuthorizationMode
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.protocols import HandlerSessionProvider
from fastapi_mergen.core.retry import RetryPolicy
from fastapi_mergen.core.routing import RouteRegistry, RouteSpecification
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_mergen.delegation.signing import DelegationIssuer, DelegationVerifier
from fastapi_mergen.errors import (
    AuthorizationDenied,
    LeaseLost,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_mergen.handlers.dependencies import tenant_session_provider
from fastapi_mergen.handlers.executor import HandlerExecutor
from fastapi_mergen.postgres.leasing import ClaimedDelivery, LeaseRepository
from fastapi_mergen.postgres.relay import PollingRelay
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.store import PostgresStore
from fastapi_mergen.sqlalchemy.models import SCHEMA, AttemptRow, DeliveryRow, EventRow
from fastapi_mergen.sqlalchemy.repository import delivery_from_row
from fastapi_mergen.sqlalchemy.uow import MergenUnitOfWork
from fastapi_mergen.testing.evidence import postgres_evidence_metadata

_BUSINESS_TABLE = f"{SCHEMA}.conformance_business"


class _ZeroRandom:
    def uniform(self, lower: float, upper: float) -> float:
        del lower, upper
        return 0.0


class _DelegationClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 25, 12, 5, tzinfo=UTC)


class PostgresBoundaryDriver:
    """Trusted test adapter; production operations still use public runtime paths."""

    def __init__(
        self,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> None:
        self._migration_engine = migration_engine
        self._app_sessions = async_sessionmaker(app_engine, expire_on_commit=False)
        self._relay_sessions = async_sessionmaker(relay_engine, expire_on_commit=False)
        self._roles = roles
        self._leases = LeaseRepository(random_source=_ZeroRandom())
        delegation_keys = InMemoryKeyRing(
            (SigningKey(key_id="conformance-v1", secret=secrets.token_bytes(32)),)
        )
        self._delegation_issuer = DelegationIssuer(
            issuer="fastapi-mergen-conformance",
            keys=delegation_keys,
            clock=_DelegationClock(),
        )
        self._delegation_verifier = DelegationVerifier(
            issuer="fastapi-mergen-conformance",
            keys=delegation_keys,
            clock=_DelegationClock(),
        )
        self._claims: dict[UUID, ClaimedDelivery] = {}
        self._evidence: dict[str, int] = {"published": 0, "finalized": 0}
        self._manifest_metadata: dict[str, JsonValue] = {
            "package.version": __version__,
            "implementation.commit": "unavailable",
            "database.product": "PostgreSQL",
            "database.version": "unavailable",
            "database.driver": "asyncpg",
            "database.driver_version": "unavailable",
            "schema.revisions": {},
        }

    @classmethod
    async def create(
        cls,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> PostgresBoundaryDriver:
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
        return CapabilityManifest(
            adapter_name="fastapi-mergen-postgresql-core",
            adapter_version=__version__,
            implementation="fastapi_mergen.testing.postgres_driver.PostgresBoundaryDriver",
            capabilities=frozenset(
                {
                    Capability.TRANSACTIONAL_EFFECTS,
                    Capability.TENANT_ISOLATION,
                    Capability.AUTHORIZATION,
                    Capability.DELIVERY_LEASES,
                    Capability.CONTEXT_LIFECYCLE,
                    Capability.DELEGATION,
                }
            ),
            invariants=frozenset(
                {
                    Invariant.ATOMIC_INTENT,
                    Invariant.TENANT_CONTINUITY,
                    Invariant.AUTHORITY_PROVENANCE,
                    Invariant.STABLE_RETRY_IDENTITY,
                    Invariant.INDEPENDENT_FANOUT,
                    Invariant.CAUSAL_LINEAGE,
                    Invariant.REPLAY_ACCOUNTABILITY,
                    Invariant.LEASE_FENCING,
                    Invariant.CONTEXT_CLEANUP,
                    Invariant.SECRET_MINIMIZATION,
                    Invariant.DELEGATION_BINDING,
                }
            ),
            metadata=dict(self._manifest_metadata),
        )

    async def reset(self) -> None:
        async with self._migration_engine.begin() as connection:
            await connection.execute(text(f"DELETE FROM {_BUSINESS_TABLE}"))
            await connection.execute(text(f"DELETE FROM {SCHEMA}.attempts"))
            await connection.execute(text(f"DELETE FROM {SCHEMA}.deliveries"))
            await connection.execute(text(f"DELETE FROM {SCHEMA}.events"))
        self._claims.clear()
        self._evidence = {"published": 0, "finalized": 0}

    async def close(self) -> None:
        self._claims.clear()

    async def public_evidence(self) -> dict[str, int]:
        return dict(self._evidence)

    async def publish(
        self,
        *,
        principal: Principal,
        business_key: str,
        event_type: str,
        destinations: Sequence[str],
        correlation_id: UUID,
        causation_id: UUID | None,
        commit: bool,
    ) -> PublishedEvent | None:
        routes = tuple(
            _route(event_type, destination, index) for index, destination in enumerate(destinations)
        )
        record = None
        try:
            async with self._app_sessions() as session:
                uow = MergenUnitOfWork(
                    session=session,
                    principal=principal,
                    store=PostgresStore(),
                    routes=routes,
                )
                async with uow:
                    await session.execute(
                        text(
                            f"INSERT INTO {_BUSINESS_TABLE}(tenant_id, business_key) "
                            "VALUES (:tenant, :key)"
                        ),
                        {"tenant": principal.tenant_id, "key": business_key},
                    )
                    record = await uow.emit(
                        Event(
                            type=event_type,
                            version=1,
                            data={"business_key": business_key},
                            correlation_id=correlation_id,
                            causation_id=causation_id,
                        )
                    )
                    if not commit:
                        raise _RollbackRequested
        except _RollbackRequested:
            return None
        if record is None:
            raise RuntimeError("Committed publication did not return an event record.")
        async with self._relay_sessions() as session:
            rows = (
                await session.scalars(
                    select(DeliveryRow)
                    .where(
                        DeliveryRow.tenant_id == principal.tenant_id,
                        DeliveryRow.event_id == record.event_id,
                    )
                    .order_by(DeliveryRow.route_key)
                )
            ).all()
        self._evidence["published"] += 1
        return PublishedEvent(
            event_id=record.event_id,
            tenant_id=principal.tenant_id,
            delivery_ids=tuple(row.delivery_id for row in rows),
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    async def snapshot(
        self,
        *,
        principal: Principal,
        tenant_id: UUID,
    ) -> BoundarySnapshot:
        async with self._app_sessions() as session, session.begin():
            await _bind_tenant(session, principal)
            business_keys = tuple(
                (
                    await session.scalars(
                        text(
                            f"SELECT business_key FROM {_BUSINESS_TABLE} "
                            "WHERE tenant_id = :tenant ORDER BY business_key"
                        ),
                        {"tenant": tenant_id},
                    )
                ).all()
            )
            event_ids = tuple(
                (
                    await session.scalars(
                        select(EventRow.event_id)
                        .where(EventRow.tenant_id == tenant_id)
                        .order_by(EventRow.created_at)
                    )
                ).all()
            )
            deliveries = (
                await session.scalars(
                    select(DeliveryRow)
                    .where(DeliveryRow.tenant_id == tenant_id)
                    .order_by(DeliveryRow.route_key)
                )
            ).all()
            views = tuple([await _delivery_view(session, row) for row in deliveries])
        if principal.tenant_id != tenant_id:
            if business_keys or event_ids or views:
                raise AssertionError("PostgreSQL RLS exposed cross-tenant boundary state.")
            raise ConformanceAccessDenied
        return BoundarySnapshot(
            business_keys=business_keys,
            event_ids=event_ids,
            deliveries=views,
        )

    async def claim(self, *, delivery_id: UUID, worker_id: str) -> LeaseView:
        del worker_id
        cached = self._claims.get(delivery_id)
        if cached is None:
            async with self._relay_sessions() as session:
                claims = await self._leases.claim(
                    session,
                    now=datetime.now(UTC),
                    batch_size=100,
                    per_tenant=100,
                )
            self._claims.update({claim.delivery.delivery_id: claim for claim in claims})
            cached = self._claims.get(delivery_id)
        if cached is None:
            raise RuntimeError("Requested delivery was not claimable.")
        return LeaseView(
            delivery_id=delivery_id,
            attempt_id=cached.attempt.attempt_id,
            lease_token=cached.lease_token,
            message_id=str(delivery_id),
        )

    async def finalize(self, *, lease: LeaseView, outcome: str) -> DeliveryView:
        claim = self._claims.get(lease.delivery_id)
        if claim is None or claim.lease_token != lease.lease_token:
            raise ConformanceLeaseLost
        try:
            relay = PollingRelay(
                sessions=self._relay_sessions,
                leases=self._leases,
                sink=_ConformanceRelaySink(self, outcome),
            )
            await relay.execute_claim(claim)
        except LeaseLost as exc:
            raise ConformanceLeaseLost from exc
        self._claims.pop(lease.delivery_id, None)
        self._evidence["finalized"] += 1
        return await self.delivery(delivery_id=lease.delivery_id)

    async def delivery(self, *, delivery_id: UUID) -> DeliveryView:
        async with self._relay_sessions() as session:
            row = await session.scalar(
                select(DeliveryRow).where(DeliveryRow.delivery_id == delivery_id)
            )
            if row is None:
                raise LookupError("Delivery not found.")
            return await _delivery_view(session, row)

    async def replay(
        self,
        *,
        delivery_id: UUID,
        reason: str,
        subject_id: str,
    ) -> DeliveryView:
        original = await self._delivery_record(delivery_id)
        async with self._relay_sessions() as session:
            replay = await self._leases.replay(
                session,
                tenant_id=original.tenant_id,
                delivery_id=delivery_id,
                actor=subject_id,
                reason=reason,
                now=datetime.now(UTC),
            )
        return await self.delivery(delivery_id=replay.delivery_id)

    async def resolve_authority(
        self,
        *,
        origin: Principal,
        required_scopes: frozenset[str],
        route_allowed_scopes: frozenset[str],
        mode: AuthorizationMode,
        current_scopes: frozenset[str] | None = None,
        service_capabilities: frozenset[str] | None = None,
    ) -> AuthorityView:
        if mode is AuthorizationMode.SNAPSHOT:
            effective = origin.scopes & route_allowed_scopes
            provenance = "snapshot"
        elif mode is AuthorizationMode.REVALIDATE:
            effective = origin.scopes & route_allowed_scopes & (current_scopes or frozenset())
            provenance = "revalidate"
        else:
            effective = route_allowed_scopes & (service_capabilities or frozenset())
            provenance = "service_policy"
        effective &= required_scopes
        return AuthorityView(
            effective_scopes=effective,
            provenance=provenance,
            origin_ceiling=origin.scopes,
        )

    async def run_in_context(
        self,
        *,
        principal: Principal,
        callback: Callable[[], Awaitable[object]],
    ) -> object:
        with principal_context(principal):
            return await callback()

    def current_principal(self) -> Principal | None:
        return current_principal(required=False)

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
        return self._delegation_issuer.mint(
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
        try:
            claims = self._delegation_verifier.verify(
                token=token,
                audience=audience,
                method=method,
                path=path,
                required_scopes=required_scopes,
            )
        except AuthorizationDenied as exc:
            raise ConformanceAccessDenied from exc
        return DelegationView(
            tenant_id=claims.tenant_id,
            subject_id=claims.subject_id,
            actor_id=claims.actor_id,
            client_id=claims.client_id,
            scopes=frozenset(claims.scopes),
            audience=claims.audience,
            method=claims.method,
            path=claims.path,
        )

    async def _delivery_record(self, delivery_id: UUID) -> DeliveryRecord:
        async with self._relay_sessions() as session:
            row = await session.scalar(
                select(DeliveryRow).where(DeliveryRow.delivery_id == delivery_id)
            )
        if row is None:
            raise LookupError("Delivery not found.")
        return delivery_from_row(row)

    async def _execute_handler(self, claim: ClaimedDelivery) -> None:
        if claim.delivery.destination_kind != "handler":
            return

        async def handler(context: EffectContext[object]) -> None:
            async with context.application_session() as session:
                tenant = await session.scalar(
                    text("SELECT nullif(current_setting('mergen.tenant_id', true), '')")
                )
                subject = await session.scalar(
                    text("SELECT nullif(current_setting('mergen.subject_id', true), '')")
                )
            if str(tenant) != str(context.principal.tenant_id):
                raise AssertionError("Handler application session lost tenant continuity.")
            if str(subject) != context.principal.subject_id:
                raise AssertionError("Handler application session lost subject continuity.")
            self._evidence["handled"] = self._evidence.get("handled", 0) + 1

        snapshot = claim.route_snapshot
        authority = snapshot["authority"]
        destination = snapshot["destination"]
        retry = snapshot["retry"]
        if not isinstance(authority, dict) or not isinstance(destination, dict):
            raise AssertionError("Conformance handler snapshot is malformed.")
        if not isinstance(retry, dict):
            raise AssertionError("Conformance handler retry policy is malformed.")
        specification = RouteSpecification(
            event_type=claim.event.event_type,
            route_key=claim.delivery.route_key,
            version=claim.delivery.route_version,
            destination_kind="handler",
            destination_key=str(destination["key"]),
            required_scopes=tuple(authority["required_scopes"]),
            authorization=AuthorizationMode.parse(authority["mode"]),
            service_policy=None,
            service_capabilities=None,
            maximum_snapshot_age_seconds=int(authority["maximum_snapshot_age_seconds"]),
            retry_policy=RetryPolicy.from_dict(retry),
        )
        registry = RouteRegistry()
        registry.register_route(specification, handler)
        registry.freeze()
        executor = HandlerExecutor(
            registry=registry,
            clock=SystemClock(),
            application_sessions=cast(
                HandlerSessionProvider,
                tenant_session_provider(self._app_sessions),
            ),
        )
        await executor.execute(claim)

    async def _prepare_business_table(self) -> None:
        roles = self._roles
        async with self._migration_engine.begin() as connection:
            await connection.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {_BUSINESS_TABLE} ("
                    "tenant_id uuid NOT NULL, business_key text NOT NULL, "
                    "PRIMARY KEY (tenant_id, business_key))"
                )
            )
            await connection.execute(
                text(f"ALTER TABLE {_BUSINESS_TABLE} ENABLE ROW LEVEL SECURITY")
            )
            await connection.execute(
                text(f"ALTER TABLE {_BUSINESS_TABLE} FORCE ROW LEVEL SECURITY")
            )
            for suffix in ("application", "migration"):
                await connection.execute(
                    text(f"DROP POLICY IF EXISTS conformance_{suffix} ON {_BUSINESS_TABLE}")
                )
            await connection.execute(
                text(
                    f"CREATE POLICY conformance_application ON {_BUSINESS_TABLE} "
                    f"FOR ALL TO {roles.application} "
                    "USING (tenant_id = "
                    "nullif(current_setting('mergen.tenant_id', true), '')::uuid) "
                    "WITH CHECK (tenant_id = "
                    "nullif(current_setting('mergen.tenant_id', true), '')::uuid)"
                )
            )
            await connection.execute(
                text(
                    f"CREATE POLICY conformance_migration ON {_BUSINESS_TABLE} "
                    f"FOR ALL TO {roles.migration} USING (true) WITH CHECK (true)"
                )
            )
            await connection.execute(
                text(f"GRANT SELECT, INSERT ON {_BUSINESS_TABLE} TO {roles.application}")
            )


class _RollbackRequested(Exception):
    pass


class _ConformanceRelaySink:
    def __init__(self, driver: PostgresBoundaryDriver, outcome: str) -> None:
        self._driver = driver
        self._outcome = outcome

    async def execute(self, claim: ClaimedDelivery) -> None:
        if self._outcome == "succeeded":
            await self._driver._execute_handler(claim)
            return
        if self._outcome == "retryable_failure":
            raise RetryableDeliveryError(
                code="conformance.retryable",
                summary="Injected retryable conformance outcome.",
            )
        if self._outcome == "terminal_failure":
            raise PermanentDeliveryError(
                code="conformance.terminal",
                summary="Injected terminal conformance outcome.",
            )
        raise ValueError("Unsupported conformance outcome.")


def _route(event_type: str, destination: str, index: int) -> RouteSpecification:
    kind, separator, key = destination.partition(":")
    if not separator:
        kind, key = "handler", destination
    route_key = f"conformance.{index}.{kind}.{key}".replace("_", "-")
    return RouteSpecification(
        event_type=event_type,
        route_key=route_key,
        version=1,
        destination_kind=kind,
        destination_key=f"{kind}.{key}".replace("_", "-"),
        required_scopes=(),
        authorization=AuthorizationMode.SNAPSHOT,
        service_policy=None,
        service_capabilities=None,
        maximum_snapshot_age_seconds=315_360_000,
        retry_policy=RetryPolicy(
            name="conformance",
            max_attempts=4,
            base_delay_seconds=0,
            maximum_delay_seconds=0,
            handler_timeout_seconds=1,
            lease_duration_seconds=10,
        ),
    )


async def _bind_tenant(session: AsyncSession, principal: Principal) -> None:
    await session.execute(
        text("SELECT set_config('mergen.tenant_id', :tenant, true)"),
        {"tenant": str(principal.tenant_id)},
    )
    await session.execute(
        text("SELECT set_config('mergen.subject_id', :subject, true)"),
        {"subject": principal.subject_id},
    )


async def _delivery_view(session: AsyncSession, row: DeliveryRow) -> DeliveryView:
    attempts = tuple(
        (
            await session.scalars(
                select(AttemptRow.attempt_id)
                .where(
                    AttemptRow.tenant_id == row.tenant_id,
                    AttemptRow.delivery_id == row.delivery_id,
                )
                .order_by(AttemptRow.attempt_number)
            )
        ).all()
    )
    return DeliveryView(
        delivery_id=row.delivery_id,
        event_id=row.event_id,
        tenant_id=row.tenant_id,
        destination=f"{row.destination_kind}:{row.destination_key}",
        status=row.state,
        message_id=str(row.delivery_id),
        attempt_ids=attempts,
        replay_of=row.replay_of,
    )


__all__ = ["PostgresBoundaryDriver"]

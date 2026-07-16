"""Facet protocols implemented by systems under conformance test."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.core.policy import AuthorizationMode
from fastapi_mergen.core.principal import Principal

JsonMapping = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PublishedEvent:
    """Stable identifiers produced by one committed publication."""

    event_id: UUID
    tenant_id: UUID
    delivery_ids: tuple[UUID, ...]
    correlation_id: UUID
    causation_id: UUID | None


@dataclass(frozen=True, slots=True)
class DeliveryView:
    """Transport-independent delivery observation."""

    delivery_id: UUID
    event_id: UUID
    tenant_id: UUID
    destination: str
    status: str
    message_id: str
    attempt_ids: tuple[UUID, ...]
    replay_of: UUID | None = None


@dataclass(frozen=True, slots=True)
class BoundarySnapshot:
    """Tenant-visible state used by atomicity and lineage scenarios."""

    business_keys: tuple[str, ...]
    event_ids: tuple[UUID, ...]
    deliveries: tuple[DeliveryView, ...]


@dataclass(frozen=True, slots=True)
class LeaseView:
    """One claim identity used for compare-and-set finalization."""

    delivery_id: UUID
    attempt_id: UUID
    lease_token: UUID
    message_id: str


@dataclass(frozen=True, slots=True)
class AuthorityView:
    """Effective authority and its explicit provenance."""

    effective_scopes: frozenset[str]
    provenance: str
    origin_ceiling: frozenset[str]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of one protected command submission."""

    executed: bool
    replayed: bool
    response_digest: str
    generation: int




@dataclass(frozen=True, slots=True)
class WebhookAttemptView:
    """Observable properties of one outbound webhook attempt."""

    message_id: str
    attempt_no: int
    request_body_digest: str
    signed_body_digest: str
    signature_count: int
    connected_ip: str
    status_code: int
    response_body_persisted: bool


@dataclass(frozen=True, slots=True)
class ExecutorHandoffView:
    """Observable state of one external-executor handoff."""

    handoff_id: UUID
    delivery_id: UUID
    attempt_id: UUID
    task_id: str
    status: str
    terminal: bool
    execution_count: int
    tenant_id: UUID
    subject_id: str
    scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class DelegationView:
    """Verified next-hop delegated identity."""

    tenant_id: UUID
    subject_id: str
    actor_id: str | None
    client_id: str | None
    scopes: frozenset[str]
    audience: str
    method: str
    path: str


class ConformanceAccessDenied(Exception):
    """Expected cross-tenant or authorization denial."""


class ConformanceConflict(Exception):
    """Expected immutable identity conflict."""


class ConformanceLeaseLost(Exception):
    """Expected stale-lease compare-and-set rejection."""


@runtime_checkable
class BoundaryDriver(Protocol):
    """Minimum lifecycle shared by every conformance driver."""

    @property
    def manifest(self) -> CapabilityManifest: ...

    async def reset(self) -> None: ...

    async def close(self) -> None: ...

    async def public_evidence(self) -> JsonMapping: ...


@runtime_checkable
class TransactionalEffectsFacet(Protocol):
    """Commit/rollback and tenant-visible effect operations."""

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
    ) -> PublishedEvent | None: ...

    async def snapshot(
        self,
        *,
        principal: Principal,
        tenant_id: UUID,
    ) -> BoundarySnapshot: ...


@runtime_checkable
class DeliveryLeaseFacet(Protocol):
    """Lease, retry, terminal-state, and replay operations."""

    async def claim(self, *, delivery_id: UUID, worker_id: str) -> LeaseView: ...

    async def finalize(
        self,
        *,
        lease: LeaseView,
        outcome: str,
    ) -> DeliveryView: ...

    async def delivery(self, *, delivery_id: UUID) -> DeliveryView: ...

    async def replay(
        self,
        *,
        delivery_id: UUID,
        reason: str,
        subject_id: str,
    ) -> DeliveryView: ...


@runtime_checkable
class AuthorizationFacet(Protocol):
    """Resolve one explicit authorization mode without expanding authority."""

    async def resolve_authority(
        self,
        *,
        origin: Principal,
        required_scopes: frozenset[str],
        route_allowed_scopes: frozenset[str],
        mode: AuthorizationMode,
        current_scopes: frozenset[str] | None = None,
        service_capabilities: frozenset[str] | None = None,
    ) -> AuthorityView: ...


@runtime_checkable
class ContextLifecycleFacet(Protocol):
    """Bind one principal around a callback and reset it afterwards."""

    async def run_in_context(
        self,
        *,
        principal: Principal,
        callback: Callable[[], Awaitable[object]],
    ) -> object: ...

    def current_principal(self) -> Principal | None: ...


@runtime_checkable
class CommandIdempotencyFacet(Protocol):
    """Execute a command under a stable transactional identity."""

    async def execute_command(
        self,
        *,
        principal: Principal,
        route_id: str,
        method: str,
        idempotency_key: str,
        request_fingerprint: str,
        operation: Callable[[], Awaitable[str]],
    ) -> CommandResult: ...


@runtime_checkable
class DelegationFacet(Protocol):
    """Mint and verify target-bound attenuated delegation credentials."""

    async def mint_delegation(
        self,
        *,
        principal: Principal,
        audience: str,
        method: str,
        path: str,
        scopes: frozenset[str],
        ttl: timedelta,
    ) -> str: ...

    async def verify_delegation(
        self,
        *,
        token: str,
        audience: str,
        method: str,
        path: str,
        required_scopes: frozenset[str],
    ) -> DelegationView: ...

@runtime_checkable
class WebhookFacet(Protocol):
    """Deliver signed bytes through an attempt-time validated endpoint."""

    async def deliver_webhook(
        self,
        *,
        message_id: str,
        body: bytes,
        endpoint_url: str,
        resolved_addresses: Sequence[str],
        attempt_no: int,
    ) -> WebhookAttemptView: ...


@runtime_checkable
class ExternalExecutorFacet(Protocol):
    """Create and execute a durable, principal-preserving handoff."""

    async def enqueue_handoff(
        self,
        *,
        principal: Principal,
        delivery_id: UUID,
        attempt_id: UUID,
    ) -> ExecutorHandoffView: ...

    async def execute_handoff(
        self,
        *,
        handoff_id: UUID,
        worker_id: str,
    ) -> ExecutorHandoffView: ...

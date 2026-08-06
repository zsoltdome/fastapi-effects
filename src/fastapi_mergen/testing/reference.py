"""Deterministic in-memory implementation of every conformance facet.

This driver is not a production effect store.  It is a specification oracle used
to validate the runner, reporters, custom scenarios, and failure detection.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi_mergen.conformance.contract import Capability, Invariant
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.protocols import (
    AuthorityView,
    BoundarySnapshot,
    CommandResult,
    ConformanceAccessDenied,
    ConformanceConflict,
    ConformanceLeaseLost,
    DelegationView,
    DeliveryView,
    ExecutorHandoffView,
    LeaseView,
    PublishedEvent,
    WebhookAttemptView,
)
from fastapi_mergen.core.policy import AuthorizationMode
from fastapi_mergen.core.principal import Principal

_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_PATH = re.compile(r"^/(?:[A-Za-z0-9._~!$&'()*+,;=:@%-]+/?)*$")


class Fault(StrEnum):
    """Intentional invariant violations used to prove the suite catches defects."""

    COMMIT_PARTIAL = "commit_partial"
    ROLLBACK_LEAK = "rollback_leak"
    CROSS_TENANT_READ = "cross_tenant_read"
    AUTHORITY_EXPANSION = "authority_expansion"
    RETRY_IDENTITY_CHANGES = "retry_identity_changes"
    FANOUT_COUPLED = "fanout_coupled"
    LINEAGE_DROPPED = "lineage_dropped"
    REPLAY_MUTATES_ORIGINAL = "replay_mutates_original"
    STALE_LEASE_ACCEPTED = "stale_lease_accepted"
    CONTEXT_LEAK = "context_leak"
    SECRET_EVIDENCE = "secret_evidence"
    DUPLICATE_COMMAND = "duplicate_command"
    FINGERPRINT_REUSE = "fingerprint_reuse"
    LOOSE_DELEGATION_TARGET = "loose_delegation_target"
    WEBHOOK_UNSIGNED_BODY = "webhook_unsigned_body"
    WEBHOOK_SSRF_ALLOWED = "webhook_ssrf_allowed"
    WEBHOOK_RESPONSE_PERSISTED = "webhook_response_persisted"
    EXECUTOR_ENQUEUE_TERMINAL = "executor_enqueue_terminal"
    EXECUTOR_DUPLICATE_EXECUTION = "executor_duplicate_execution"
    EXECUTOR_PRINCIPAL_LOST = "executor_principal_lost"


@dataclass(slots=True)
class _EventRecord:
    event_id: UUID
    tenant_id: UUID
    correlation_id: UUID
    causation_id: UUID | None


@dataclass(slots=True)
class _DeliveryRecord:
    delivery_id: UUID
    event_id: UUID
    tenant_id: UUID
    destination: str
    status: str
    message_id: str
    attempt_ids: list[UUID]
    active_lease_token: UUID | None = None
    replay_of: UUID | None = None


@dataclass(slots=True)
class _HandoffRecord:
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
class _CommandRecord:
    subject_id: str
    fingerprint: str
    response_digest: str
    generation: int


class ReferenceBoundaryDriver:
    """Complete Boundary Contract reference driver with injectable faults."""

    def __init__(self, *, faults: Sequence[Fault | str] = ()) -> None:
        self._faults = frozenset(Fault(item) for item in faults)
        self._principal: ContextVar[Principal | None] = ContextVar(
            "mergen_reference_principal", default=None
        )
        self._counter = 0
        self._business: dict[UUID, list[str]] = {}
        self._events: dict[UUID, _EventRecord] = {}
        self._deliveries: dict[UUID, _DeliveryRecord] = {}
        self._commands: dict[tuple[UUID, str, str, str], _CommandRecord] = {}
        self._command_locks: dict[tuple[UUID, str, str, str], asyncio.Lock] = {}
        self._handoffs: dict[UUID, _HandoffRecord] = {}
        self._delegation_secret = b"conformance-secret-canary-reference-key"
        self._closed = False
        self._manifest = CapabilityManifest(
            adapter_name="Mergen reference driver",
            adapter_version="1.0.0",
            implementation="fastapi_mergen.testing.reference",
            capabilities=frozenset(Capability),
            invariants=frozenset(Invariant),
            metadata={
                "purpose": "deterministic specification oracle",
                "storage": "memory",
                "fault_count": len(self._faults),
            },
        )

    @property
    def manifest(self) -> CapabilityManifest:
        return self._manifest

    async def reset(self) -> None:
        self._counter = 0
        self._business.clear()
        self._events.clear()
        self._deliveries.clear()
        self._commands.clear()
        self._command_locks.clear()
        self._handoffs.clear()
        self._principal = ContextVar("mergen_reference_principal", default=None)
        self._closed = False

    async def close(self) -> None:
        self._principal = ContextVar("mergen_reference_principal", default=None)
        self._closed = True

    async def public_evidence(self) -> Mapping[str, object]:
        evidence: dict[str, object] = {
            "adapter": self._manifest.adapter_name,
            "events": len(self._events),
            "deliveries": len(self._deliveries),
            "closed": self._closed,
            "key_id": "reference-signing-key",
            "credential_ref": "reference-credential",
        }
        if Fault.SECRET_EVIDENCE in self._faults:
            evidence["diagnostic"] = "conformance-secret-canary"
        return evidence

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
        del event_type
        event_id = self._uuid("event")
        delivery_ids = tuple(self._uuid(f"delivery:{destination}") for destination in destinations)
        if not commit:
            if Fault.ROLLBACK_LEAK in self._faults:
                self._business.setdefault(principal.tenant_id, []).append(business_key)
            return None
        self._business.setdefault(principal.tenant_id, []).append(business_key)
        if Fault.COMMIT_PARTIAL not in self._faults:
            self._events[event_id] = _EventRecord(
                event_id=event_id,
                tenant_id=principal.tenant_id,
                correlation_id=(
                    UUID(int=0) if Fault.LINEAGE_DROPPED in self._faults else correlation_id
                ),
                causation_id=(None if Fault.LINEAGE_DROPPED in self._faults else causation_id),
            )
            for delivery_id, destination in zip(delivery_ids, destinations, strict=True):
                self._deliveries[delivery_id] = _DeliveryRecord(
                    delivery_id=delivery_id,
                    event_id=event_id,
                    tenant_id=principal.tenant_id,
                    destination=destination,
                    status="pending",
                    message_id=f"msg_{delivery_id.hex}",
                    attempt_ids=[],
                )
        return PublishedEvent(
            event_id=event_id,
            tenant_id=principal.tenant_id,
            delivery_ids=delivery_ids,
            correlation_id=(
                UUID(int=0) if Fault.LINEAGE_DROPPED in self._faults else correlation_id
            ),
            causation_id=(None if Fault.LINEAGE_DROPPED in self._faults else causation_id),
        )

    async def snapshot(
        self,
        *,
        principal: Principal,
        tenant_id: UUID,
    ) -> BoundarySnapshot:
        if principal.tenant_id != tenant_id and Fault.CROSS_TENANT_READ not in self._faults:
            raise ConformanceAccessDenied
        business = tuple(self._business.get(tenant_id, ()))
        events = tuple(
            record.event_id for record in self._events.values() if record.tenant_id == tenant_id
        )
        deliveries = tuple(
            self._view(record)
            for record in self._deliveries.values()
            if record.tenant_id == tenant_id
        )
        return BoundarySnapshot(business_keys=business, event_ids=events, deliveries=deliveries)

    async def claim(self, *, delivery_id: UUID, worker_id: str) -> LeaseView:
        del worker_id
        record = self._deliveries[delivery_id]
        if record.status not in {"pending", "retry_wait"}:
            raise ConformanceConflict
        attempt_id = self._uuid(f"attempt:{delivery_id}")
        lease_token = self._uuid(f"lease:{delivery_id}")
        record.attempt_ids.append(attempt_id)
        record.active_lease_token = lease_token
        record.status = "leased"
        message_id = record.message_id
        if Fault.RETRY_IDENTITY_CHANGES in self._faults and len(record.attempt_ids) > 1:
            message_id = f"msg_retry_{attempt_id.hex}"
        return LeaseView(
            delivery_id=delivery_id,
            attempt_id=attempt_id,
            lease_token=lease_token,
            message_id=message_id,
        )

    async def finalize(self, *, lease: LeaseView, outcome: str) -> DeliveryView:
        record = self._deliveries[lease.delivery_id]
        if (
            record.status != "leased" or record.active_lease_token != lease.lease_token
        ) and Fault.STALE_LEASE_ACCEPTED not in self._faults:
            raise ConformanceLeaseLost
        if outcome == "succeeded":
            record.status = "succeeded"
        elif outcome == "retryable_failure":
            record.status = "retry_wait"
        elif outcome == "terminal_failure":
            record.status = "dead"
        else:
            raise ValueError("unknown outcome")
        record.active_lease_token = None
        if Fault.FANOUT_COUPLED in self._faults:
            for other in self._deliveries.values():
                if other.event_id == record.event_id and other.delivery_id != record.delivery_id:
                    other.status = record.status
        return self._view(record)

    async def delivery(self, *, delivery_id: UUID) -> DeliveryView:
        return self._view(self._deliveries[delivery_id])

    async def replay(
        self,
        *,
        delivery_id: UUID,
        reason: str,
        subject_id: str,
    ) -> DeliveryView:
        del reason, subject_id
        original = self._deliveries[delivery_id]
        if Fault.REPLAY_MUTATES_ORIGINAL in self._faults:
            original.status = "pending"
            return self._view(original)
        replay_id = self._uuid(f"replay:{delivery_id}")
        replay = _DeliveryRecord(
            delivery_id=replay_id,
            event_id=original.event_id,
            tenant_id=original.tenant_id,
            destination=original.destination,
            status="pending",
            message_id=f"msg_{replay_id.hex}",
            attempt_ids=[],
            replay_of=original.delivery_id,
        )
        self._deliveries[replay_id] = replay
        return self._view(replay)

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
            effective = (current_scopes or frozenset()) & origin.scopes & route_allowed_scopes
            provenance = "revalidate"
        else:
            effective = (service_capabilities or frozenset()) & route_allowed_scopes
            provenance = "service_policy"
        if Fault.AUTHORITY_EXPANSION in self._faults:
            effective = route_allowed_scopes
        if not required_scopes.issubset(effective):
            raise ConformanceAccessDenied
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
        token: Token[Principal | None] = self._principal.set(principal)
        try:
            return await callback()
        finally:
            if Fault.CONTEXT_LEAK not in self._faults:
                self._principal.reset(token)

    def current_principal(self) -> Principal | None:
        return self._principal.get()

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
        if not _HEX_DIGEST.fullmatch(request_fingerprint):
            raise ValueError("invalid request fingerprint")
        key_digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        identity = (principal.tenant_id, route_id, method.upper(), key_digest)
        if Fault.DUPLICATE_COMMAND in self._faults:
            response = await operation()
            return CommandResult(
                executed=True,
                replayed=False,
                response_digest=response,
                generation=1,
            )
        lock = self._command_locks.setdefault(identity, asyncio.Lock())
        async with lock:
            existing = self._commands.get(identity)
            if existing is not None:
                if (
                    existing.fingerprint != request_fingerprint
                    or existing.subject_id != principal.subject_id
                ) and Fault.FINGERPRINT_REUSE not in self._faults:
                    raise ConformanceConflict
                return CommandResult(
                    executed=False,
                    replayed=True,
                    response_digest=existing.response_digest,
                    generation=existing.generation,
                )
            response = await operation()
            if not _HEX_DIGEST.fullmatch(response):
                raise ValueError("operation response must be a SHA-256 digest")
            record = _CommandRecord(
                subject_id=principal.subject_id,
                fingerprint=request_fingerprint,
                response_digest=response,
                generation=1,
            )
            self._commands[identity] = record
            return CommandResult(
                executed=True,
                replayed=False,
                response_digest=response,
                generation=record.generation,
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
        parsed = urlsplit(endpoint_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or attempt_no < 1
            or not resolved_addresses
        ):
            raise ConformanceAccessDenied
        addresses = tuple(ipaddress.ip_address(item) for item in resolved_addresses)
        if Fault.WEBHOOK_SSRF_ALLOWED not in self._faults and any(
            not address.is_global for address in addresses
        ):
            raise ConformanceAccessDenied
        body_digest = hashlib.sha256(body).hexdigest()
        signed_digest = body_digest
        if Fault.WEBHOOK_UNSIGNED_BODY in self._faults:
            signed_digest = hashlib.sha256(body + b"changed").hexdigest()
        hmac.new(
            self._delegation_secret,
            f"{message_id}.{attempt_no}.".encode() + body,
            hashlib.sha256,
        ).digest()
        return WebhookAttemptView(
            message_id=message_id,
            attempt_no=attempt_no,
            request_body_digest=body_digest,
            signed_body_digest=signed_digest,
            signature_count=1,
            connected_ip=str(addresses[0]),
            status_code=200,
            response_body_persisted=(Fault.WEBHOOK_RESPONSE_PERSISTED in self._faults),
        )

    async def enqueue_handoff(
        self,
        *,
        principal: Principal,
        delivery_id: UUID,
        attempt_id: UUID,
    ) -> ExecutorHandoffView:
        handoff_id = uuid5(
            NAMESPACE_URL,
            f"fastapi-mergen:handoff:{delivery_id}:{attempt_id}",
        )
        tenant_id = principal.tenant_id
        subject_id = principal.subject_id
        scopes = principal.scopes
        if Fault.EXECUTOR_PRINCIPAL_LOST in self._faults:
            tenant_id = UUID(int=0)
            subject_id = "unknown"
            scopes = frozenset()
        terminal = Fault.EXECUTOR_ENQUEUE_TERMINAL in self._faults
        record = _HandoffRecord(
            handoff_id=handoff_id,
            delivery_id=delivery_id,
            attempt_id=attempt_id,
            task_id=f"mergen-{delivery_id}-{attempt_id}",
            status="succeeded" if terminal else "enqueued",
            terminal=terminal,
            execution_count=1 if terminal else 0,
            tenant_id=tenant_id,
            subject_id=subject_id,
            scopes=scopes,
        )
        self._handoffs[handoff_id] = record
        return self._handoff_view(record)

    async def execute_handoff(
        self,
        *,
        handoff_id: UUID,
        worker_id: str,
    ) -> ExecutorHandoffView:
        del worker_id
        record = self._handoffs[handoff_id]
        if not record.terminal:
            record.execution_count += 1
            record.status = "succeeded"
            record.terminal = True
        elif Fault.EXECUTOR_DUPLICATE_EXECUTION in self._faults:
            record.execution_count += 1
        return self._handoff_view(record)

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
        if not scopes.issubset(principal.scopes):
            raise ConformanceAccessDenied
        if ttl <= timedelta(0) or ttl > timedelta(minutes=5):
            raise ValueError("ttl outside reference policy")
        target_path = self._canonical_path(path)
        now = datetime.now(UTC)
        claims = {
            "v": 1,
            "jti": self._uuid("delegation").hex,
            "tenant": str(principal.tenant_id),
            "sub": principal.subject_id,
            "actor": principal.actor_id,
            "client": principal.client_id,
            "scopes": sorted(scopes),
            "aud": audience,
            "method": method.upper(),
            "path": target_path,
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
        }
        payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._delegation_secret, payload, hashlib.sha256).digest()
        return f"{self._b64(payload)}.{self._b64(signature)}"

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
            encoded_payload, encoded_signature = token.split(".", 1)
            payload = self._unb64(encoded_payload)
            signature = self._unb64(encoded_signature)
            expected = hmac.new(self._delegation_secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ConformanceAccessDenied
            claims = json.loads(payload)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ConformanceAccessDenied from exc
        now = int(datetime.now(UTC).timestamp())
        if claims.get("v") != 1 or not claims.get("iat") <= now <= claims.get("exp"):
            raise ConformanceAccessDenied
        exact_target = (
            claims.get("aud") == audience
            and claims.get("method") == method.upper()
            and claims.get("path") == self._canonical_path(path)
        )
        if not exact_target and Fault.LOOSE_DELEGATION_TARGET not in self._faults:
            raise ConformanceAccessDenied
        scopes = frozenset(claims.get("scopes", ()))
        if not required_scopes.issubset(scopes):
            raise ConformanceAccessDenied
        return DelegationView(
            tenant_id=UUID(claims["tenant"]),
            subject_id=claims["sub"],
            actor_id=claims.get("actor"),
            client_id=claims.get("client"),
            scopes=scopes,
            audience=claims["aud"],
            method=claims["method"],
            path=claims["path"],
        )

    @staticmethod
    def _handoff_view(record: _HandoffRecord) -> ExecutorHandoffView:
        return ExecutorHandoffView(
            handoff_id=record.handoff_id,
            delivery_id=record.delivery_id,
            attempt_id=record.attempt_id,
            task_id=record.task_id,
            status=record.status,
            terminal=record.terminal,
            execution_count=record.execution_count,
            tenant_id=record.tenant_id,
            subject_id=record.subject_id,
            scopes=record.scopes,
        )

    def _view(self, record: _DeliveryRecord) -> DeliveryView:
        return DeliveryView(
            delivery_id=record.delivery_id,
            event_id=record.event_id,
            tenant_id=record.tenant_id,
            destination=record.destination,
            status=record.status,
            message_id=record.message_id,
            attempt_ids=tuple(record.attempt_ids),
            replay_of=record.replay_of,
        )

    def _uuid(self, label: str) -> UUID:
        self._counter += 1
        return uuid5(NAMESPACE_URL, f"fastapi-mergen:{label}:{self._counter}")

    @staticmethod
    def _canonical_path(path: str) -> str:
        if (
            not isinstance(path, str)
            or not _PATH.fullmatch(path)
            or "//" in path
            or "/../" in f"{path}/"
            or "/./" in f"{path}/"
            or "\\" in path
            or "%2f" in path.lower()
            or "%5c" in path.lower()
            or "%2e" in path.lower()
        ):
            raise ConformanceAccessDenied
        return path

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _unb64(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)

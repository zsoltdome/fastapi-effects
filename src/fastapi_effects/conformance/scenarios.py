"""Deterministic Boundary Contract scenario definitions."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi_effects.conformance.contract import Capability, Invariant
from fastapi_effects.conformance.protocols import (
    AuthorizationFacet,
    BoundaryDriver,
    CommandIdempotencyFacet,
    ConformanceAccessDenied,
    ConformanceConflict,
    ConformanceLeaseLost,
    ContextLifecycleFacet,
    DelegationFacet,
    DeliveryLeaseFacet,
    ExternalExecutorFacet,
    TransactionalEffectsFacet,
    WebhookFacet,
)
from fastapi_effects.core.policy import AuthorizationMode
from fastapi_effects.core.principal import Principal

TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("22222222-2222-4222-8222-222222222222")
CORRELATION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CAUSATION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


@dataclass(frozen=True, slots=True)
class ScenarioObservation:
    """Successful scenario summary and bounded evidence."""

    summary: str
    evidence: dict[str, Any]
    audit_material: object | None = None


ScenarioCallable = Callable[[BoundaryDriver], Awaitable[ScenarioObservation]]


@dataclass(frozen=True, slots=True)
class Scenario:
    """One executable check selected by profile and manifest."""

    check_id: str
    invariant: Invariant
    capability: Capability | None
    severity: str
    timeout_seconds: float
    execute: ScenarioCallable
    remediation: str


def principal(
    tenant_id: UUID = TENANT_A,
    *,
    subject_id: str = "user:alice",
    scopes: frozenset[str] = frozenset({"invoices:read", "invoices:write"}),
) -> Principal:
    """Return a deterministic, valid test principal."""

    issued = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    return Principal(
        tenant_id=tenant_id,
        subject_id=subject_id,
        actor_id="actor:operator",
        client_id="client:conformance",
        scopes=scopes,
        issued_at=issued,
        authentication_time=issued - timedelta(minutes=1),
        expires_at=issued + timedelta(hours=1),
        credential_ref="credential:test-reference",
    )


def _require(driver: BoundaryDriver, protocol: type[Any], name: str) -> Any:
    if not isinstance(driver, protocol):
        raise TypeError(f"Driver declares {name} but does not implement its facet protocol.")
    return driver


async def atomic_commit(driver: BoundaryDriver) -> ScenarioObservation:
    facet: TransactionalEffectsFacet = _require(
        driver, TransactionalEffectsFacet, Capability.TRANSACTIONAL_EFFECTS.value
    )
    actor = principal()
    published = await facet.publish(
        principal=actor,
        business_key="invoice:commit",
        event_type="invoice.created",
        destinations=("handler:pdf", "webhook:customer"),
        correlation_id=CORRELATION_ID,
        causation_id=CAUSATION_ID,
        commit=True,
    )
    if published is None:
        raise AssertionError("Committed publication returned no stable identity.")
    snapshot = await facet.snapshot(principal=actor, tenant_id=TENANT_A)
    if "invoice:commit" not in snapshot.business_keys:
        raise AssertionError("Business state did not commit with the event.")
    if published.event_id not in snapshot.event_ids:
        raise AssertionError("Event did not commit with business state.")
    visible = {delivery.delivery_id for delivery in snapshot.deliveries}
    if set(published.delivery_ids) != visible:
        raise AssertionError("Original delivery set was not committed atomically.")
    return ScenarioObservation(
        "Business state, event, and original deliveries committed together.",
        {
            "event_id": published.event_id,
            "delivery_count": len(published.delivery_ids),
            "business_key_count": len(snapshot.business_keys),
        },
    )


async def atomic_rollback(driver: BoundaryDriver) -> ScenarioObservation:
    facet: TransactionalEffectsFacet = _require(
        driver, TransactionalEffectsFacet, Capability.TRANSACTIONAL_EFFECTS.value
    )
    actor = principal()
    published = await facet.publish(
        principal=actor,
        business_key="invoice:rollback",
        event_type="invoice.created",
        destinations=("handler:pdf",),
        correlation_id=CORRELATION_ID,
        causation_id=None,
        commit=False,
    )
    if published is not None:
        raise AssertionError("Rolled-back publication returned committed identity.")
    snapshot = await facet.snapshot(principal=actor, tenant_id=TENANT_A)
    if snapshot.business_keys or snapshot.event_ids or snapshot.deliveries:
        raise AssertionError("Rolled-back work remained visible.")
    return ScenarioObservation("Rollback left no business row, event, or delivery.", {})


async def cross_tenant_denial(driver: BoundaryDriver) -> ScenarioObservation:
    facet: TransactionalEffectsFacet = _require(
        driver, TransactionalEffectsFacet, Capability.TENANT_ISOLATION.value
    )
    tenant_a = principal(TENANT_A)
    await facet.publish(
        principal=tenant_a,
        business_key="invoice:tenant-a",
        event_type="invoice.created",
        destinations=("handler:pdf",),
        correlation_id=CORRELATION_ID,
        causation_id=None,
        commit=True,
    )
    tenant_b = principal(TENANT_B, subject_id="user:bob")
    try:
        await facet.snapshot(principal=tenant_b, tenant_id=TENANT_A)
    except ConformanceAccessDenied:
        return ScenarioObservation("Cross-tenant read was denied fail-closed.", {})
    raise AssertionError("Tenant B could inspect Tenant A boundary state.")


async def authority_snapshot(driver: BoundaryDriver) -> ScenarioObservation:
    facet: AuthorizationFacet = _require(driver, AuthorizationFacet, Capability.AUTHORIZATION.value)
    origin = principal(scopes=frozenset({"invoices:read", "invoices:write", "admin"}))
    view = await facet.resolve_authority(
        origin=origin,
        required_scopes=frozenset({"invoices:read"}),
        route_allowed_scopes=frozenset({"invoices:read", "invoices:render"}),
        mode=AuthorizationMode.SNAPSHOT,
    )
    expected = frozenset({"invoices:read"})
    if view.effective_scopes != expected or view.provenance != "snapshot":
        raise AssertionError("Snapshot authority was expanded or provenance was obscured.")
    return ScenarioObservation(
        "Snapshot authority was attenuated to the origin and route intersection.",
        {"effective_scopes": sorted(view.effective_scopes), "provenance": view.provenance},
    )


async def authority_revalidate(driver: BoundaryDriver) -> ScenarioObservation:
    facet: AuthorizationFacet = _require(driver, AuthorizationFacet, Capability.AUTHORIZATION.value)
    origin = principal(scopes=frozenset({"invoices:read", "invoices:write"}))
    view = await facet.resolve_authority(
        origin=origin,
        required_scopes=frozenset({"invoices:read"}),
        route_allowed_scopes=frozenset({"invoices:read", "invoices:write", "admin"}),
        current_scopes=frozenset({"invoices:read", "admin"}),
        mode=AuthorizationMode.REVALIDATE,
    )
    if view.effective_scopes != frozenset({"invoices:read"}):
        raise AssertionError("Revalidation escaped the historical authority ceiling.")
    return ScenarioObservation(
        "Current authority was intersected with the historical ceiling.",
        {"effective_scopes": sorted(view.effective_scopes), "provenance": view.provenance},
    )


async def stable_retry_identity(driver: BoundaryDriver) -> ScenarioObservation:
    effects: TransactionalEffectsFacet = _require(
        driver, TransactionalEffectsFacet, Capability.TRANSACTIONAL_EFFECTS.value
    )
    leases: DeliveryLeaseFacet = _require(
        driver, DeliveryLeaseFacet, Capability.DELIVERY_LEASES.value
    )
    actor = principal()
    published = await effects.publish(
        principal=actor,
        business_key="invoice:retry",
        event_type="invoice.created",
        destinations=("webhook:customer",),
        correlation_id=CORRELATION_ID,
        causation_id=None,
        commit=True,
    )
    if published is None:
        raise RuntimeError("Conformance driver discarded committed publication.")
    first = await leases.claim(delivery_id=published.delivery_ids[0], worker_id="worker:one")
    await leases.finalize(lease=first, outcome="retryable_failure")
    second = await leases.claim(delivery_id=published.delivery_ids[0], worker_id="worker:two")
    if first.message_id != second.message_id:
        raise AssertionError("Automatic retry changed stable message identity.")
    if first.attempt_id == second.attempt_id:
        raise AssertionError("Automatic retry reused an attempt identity.")
    return ScenarioObservation(
        "Automatic retry kept one message identity and created a new attempt.",
        {"delivery_id": first.delivery_id, "attempts": 2, "message_id": first.message_id},
    )


async def independent_fanout(driver: BoundaryDriver) -> ScenarioObservation:
    effects: TransactionalEffectsFacet = _require(
        driver, TransactionalEffectsFacet, Capability.TRANSACTIONAL_EFFECTS.value
    )
    leases: DeliveryLeaseFacet = _require(
        driver, DeliveryLeaseFacet, Capability.DELIVERY_LEASES.value
    )
    published = await effects.publish(
        principal=principal(),
        business_key="invoice:fanout",
        event_type="invoice.created",
        destinations=("handler:pdf", "webhook:customer"),
        correlation_id=CORRELATION_ID,
        causation_id=None,
        commit=True,
    )
    if published is None:
        raise RuntimeError("Conformance driver discarded committed publication.")
    first = await leases.claim(delivery_id=published.delivery_ids[0], worker_id="worker:a")
    second = await leases.claim(delivery_id=published.delivery_ids[1], worker_id="worker:b")
    failed = await leases.finalize(lease=first, outcome="terminal_failure")
    succeeded = await leases.finalize(lease=second, outcome="succeeded")
    if failed.status != "dead" or succeeded.status != "succeeded":
        raise AssertionError("One destination outcome corrupted another destination.")
    return ScenarioObservation(
        "Fan-out destinations reached independent terminal outcomes.",
        {"statuses": sorted((failed.status, succeeded.status))},
    )


async def causal_lineage(driver: BoundaryDriver) -> ScenarioObservation:
    facet: TransactionalEffectsFacet = _require(
        driver, TransactionalEffectsFacet, Capability.TRANSACTIONAL_EFFECTS.value
    )
    published = await facet.publish(
        principal=principal(),
        business_key="invoice:lineage",
        event_type="invoice.created",
        destinations=("handler:pdf",),
        correlation_id=CORRELATION_ID,
        causation_id=CAUSATION_ID,
        commit=True,
    )
    if published is None:
        raise AssertionError("Committed event had no lineage observation.")
    if published.correlation_id != CORRELATION_ID or published.causation_id != CAUSATION_ID:
        raise AssertionError("Correlation or causation identity changed across publication.")
    return ScenarioObservation(
        "Correlation and causation identity survived publication.",
        {"correlation_id": published.correlation_id, "causation_id": published.causation_id},
    )


async def replay_accountability(driver: BoundaryDriver) -> ScenarioObservation:
    effects: TransactionalEffectsFacet = _require(
        driver, TransactionalEffectsFacet, Capability.TRANSACTIONAL_EFFECTS.value
    )
    leases: DeliveryLeaseFacet = _require(
        driver, DeliveryLeaseFacet, Capability.DELIVERY_LEASES.value
    )
    published = await effects.publish(
        principal=principal(),
        business_key="invoice:replay",
        event_type="invoice.created",
        destinations=("webhook:customer",),
        correlation_id=CORRELATION_ID,
        causation_id=None,
        commit=True,
    )
    if published is None:
        raise RuntimeError("Conformance driver discarded committed publication.")
    claim = await leases.claim(delivery_id=published.delivery_ids[0], worker_id="worker:one")
    original = await leases.finalize(lease=claim, outcome="terminal_failure")
    replay = await leases.replay(
        delivery_id=original.delivery_id,
        reason="operator-approved",
        subject_id="user:operator",
    )
    unchanged = await leases.delivery(delivery_id=original.delivery_id)
    if replay.delivery_id == original.delivery_id or replay.replay_of != original.delivery_id:
        raise AssertionError("Replay mutated or lost linkage to the original delivery.")
    if unchanged.status != "dead" or replay.message_id == original.message_id:
        raise AssertionError("Replay rewrote original history or reused message identity.")
    return ScenarioObservation(
        "Replay created a new linked delivery and preserved original history.",
        {"original_id": original.delivery_id, "replay_id": replay.delivery_id},
    )


async def lease_fencing(driver: BoundaryDriver) -> ScenarioObservation:
    effects: TransactionalEffectsFacet = _require(
        driver, TransactionalEffectsFacet, Capability.TRANSACTIONAL_EFFECTS.value
    )
    leases: DeliveryLeaseFacet = _require(
        driver, DeliveryLeaseFacet, Capability.DELIVERY_LEASES.value
    )
    published = await effects.publish(
        principal=principal(),
        business_key="invoice:lease",
        event_type="invoice.created",
        destinations=("handler:pdf",),
        correlation_id=CORRELATION_ID,
        causation_id=None,
        commit=True,
    )
    if published is None:
        raise RuntimeError("Conformance driver discarded committed publication.")
    stale = await leases.claim(delivery_id=published.delivery_ids[0], worker_id="worker:stale")
    await leases.finalize(lease=stale, outcome="retryable_failure")
    current = await leases.claim(delivery_id=published.delivery_ids[0], worker_id="worker:current")
    try:
        await leases.finalize(lease=stale, outcome="succeeded")
    except ConformanceLeaseLost:
        view = await leases.delivery(delivery_id=published.delivery_ids[0])
        if view.status != "leased":
            raise AssertionError("Stale finalization modified current lease state.") from None
        await leases.finalize(lease=current, outcome="succeeded")
        return ScenarioObservation("Stale lease token was rejected without mutation.", {})
    raise AssertionError("Stale worker finalized work after a newer claim.")


async def context_cleanup(driver: BoundaryDriver) -> ScenarioObservation:
    facet: ContextLifecycleFacet = _require(
        driver, ContextLifecycleFacet, Capability.CONTEXT_LIFECYCLE.value
    )
    observed: list[UUID | None] = []

    async def inspect() -> object:
        current = facet.current_principal()
        observed.append(None if current is None else current.tenant_id)
        return None

    await facet.run_in_context(principal=principal(TENANT_A), callback=inspect)
    if facet.current_principal() is not None:
        raise AssertionError("Principal context remained bound after first execution.")
    await facet.run_in_context(
        principal=principal(TENANT_B, subject_id="user:bob"), callback=inspect
    )
    if facet.current_principal() is not None:
        raise AssertionError("Principal context remained bound after second execution.")
    if observed != [TENANT_A, TENANT_B]:
        raise AssertionError("Sequential executions observed leaked tenant context.")
    return ScenarioObservation("Sequential principal contexts reset without leakage.", {})


async def secret_minimization(driver: BoundaryDriver) -> ScenarioObservation:
    evidence = await driver.public_evidence()
    serialized = repr(evidence).lower()
    forbidden = (
        "conformance-secret-canary",
        "bearer conformance",
        "session-cookie-canary",
        "private-key-canary",
    )
    leaked = [value for value in forbidden if value in serialized]
    if leaked:
        raise AssertionError("Public evidence exposed reusable credential material.")
    return ScenarioObservation(
        "Public evidence excluded configured secret canaries.",
        {"evidence_key_count": len(evidence)},
        audit_material=evidence,
    )


async def command_concurrency(driver: BoundaryDriver) -> ScenarioObservation:
    facet: CommandIdempotencyFacet = _require(
        driver, CommandIdempotencyFacet, Capability.COMMAND_IDEMPOTENCY.value
    )
    executions = 0
    lock = asyncio.Lock()

    async def operation() -> str:
        nonlocal executions
        async with lock:
            executions += 1
        await asyncio.sleep(0)
        return hashlib.sha256(b"invoice-created").hexdigest()

    command_principal = principal()
    fingerprint = hashlib.sha256(b"same-request").hexdigest()
    first, second = await asyncio.gather(
        facet.execute_command(
            principal=command_principal,
            route_id="invoice.create",
            method="POST",
            idempotency_key="command-42",
            request_fingerprint=fingerprint,
            operation=operation,
        ),
        facet.execute_command(
            principal=command_principal,
            route_id="invoice.create",
            method="POST",
            idempotency_key="command-42",
            request_fingerprint=fingerprint,
            operation=operation,
        ),
    )
    if executions != 1:
        raise AssertionError("Concurrent duplicate command executed more than once.")
    if first.response_digest != second.response_digest or first.executed == second.executed:
        raise AssertionError("Duplicate command did not converge to one execution and one replay.")
    return ScenarioObservation(
        "Concurrent duplicate commands converged to one transaction.",
        {"executions": executions, "generation": first.generation},
    )


async def command_conflict(driver: BoundaryDriver) -> ScenarioObservation:
    facet: CommandIdempotencyFacet = _require(
        driver, CommandIdempotencyFacet, Capability.COMMAND_IDEMPOTENCY.value
    )

    async def operation() -> str:
        return hashlib.sha256(b"first").hexdigest()

    await facet.execute_command(
        principal=principal(),
        route_id="invoice.create",
        method="POST",
        idempotency_key="command-43",
        request_fingerprint=hashlib.sha256(b"first-request").hexdigest(),
        operation=operation,
    )
    try:
        await facet.execute_command(
            principal=principal(),
            route_id="invoice.create",
            method="POST",
            idempotency_key="command-43",
            request_fingerprint=hashlib.sha256(b"different-request").hexdigest(),
            operation=operation,
        )
    except ConformanceConflict:
        return ScenarioObservation("Fingerprint mismatch produced an immutable conflict.", {})
    raise AssertionError("One idempotency identity accepted a different request fingerprint.")


async def delegation_exact_target(driver: BoundaryDriver) -> ScenarioObservation:
    facet: DelegationFacet = _require(driver, DelegationFacet, Capability.DELEGATION.value)
    origin = principal(scopes=frozenset({"billing:read", "billing:write", "admin"}))
    token = await facet.mint_delegation(
        principal=origin,
        audience="billing-api",
        method="POST",
        path="/v1/invoices/42/pay",
        scopes=frozenset({"billing:write"}),
        ttl=timedelta(minutes=2),
    )
    view = await facet.verify_delegation(
        token=token,
        audience="billing-api",
        method="POST",
        path="/v1/invoices/42/pay",
        required_scopes=frozenset({"billing:write"}),
    )
    if view.scopes != frozenset({"billing:write"}) or view.tenant_id != origin.tenant_id:
        raise AssertionError("Delegated authority changed tenant or expanded scopes.")
    return ScenarioObservation(
        "Delegation preserved principal identity and exact attenuated authority.",
        {"audience": view.audience, "method": view.method, "path": view.path},
    )


async def delegation_rejection_matrix(driver: BoundaryDriver) -> ScenarioObservation:
    facet: DelegationFacet = _require(driver, DelegationFacet, Capability.DELEGATION.value)
    origin = principal(scopes=frozenset({"billing:write"}))
    token = await facet.mint_delegation(
        principal=origin,
        audience="billing-api",
        method="POST",
        path="/v1/invoices/42/pay",
        scopes=frozenset({"billing:write"}),
        ttl=timedelta(minutes=2),
    )
    probes = (
        {"audience": "other-api", "method": "POST", "path": "/v1/invoices/42/pay"},
        {"audience": "billing-api", "method": "GET", "path": "/v1/invoices/42/pay"},
        {"audience": "billing-api", "method": "POST", "path": "/v1/invoices/43/pay"},
    )
    rejected = 0
    for probe in probes:
        try:
            await facet.verify_delegation(
                token=token,
                audience=probe["audience"],
                method=probe["method"],
                path=probe["path"],
                required_scopes=frozenset({"billing:write"}),
            )
        except ConformanceAccessDenied:
            rejected += 1
    if rejected != len(probes):
        raise AssertionError("Delegation credential was accepted for a different target.")
    return ScenarioObservation(
        "Audience, method, and path mismatch were rejected fail-closed.",
        {"rejected_probes": rejected},
    )


async def webhook_signed_retry(driver: BoundaryDriver) -> ScenarioObservation:
    facet: WebhookFacet = _require(driver, WebhookFacet, Capability.WEBHOOKS.value)
    body = b'{"event":"invoice.created","version":1}'
    first = await facet.deliver_webhook(
        message_id="msg_delivery_42",
        body=body,
        endpoint_url="https://customer.example/hooks",
        resolved_addresses=("93.184.216.34",),
        attempt_no=1,
    )
    second = await facet.deliver_webhook(
        message_id="msg_delivery_42",
        body=body,
        endpoint_url="https://customer.example/hooks",
        resolved_addresses=("93.184.216.34",),
        attempt_no=2,
    )
    if first.message_id != second.message_id:
        raise AssertionError("Webhook retry changed the stable message identity.")
    if first.request_body_digest != first.signed_body_digest:
        raise AssertionError("Webhook signature did not cover the exact sent bytes.")
    if second.request_body_digest != second.signed_body_digest:
        raise AssertionError("Webhook retry changed the signed body identity.")
    if first.request_body_digest != second.request_body_digest:
        raise AssertionError("Webhook retry changed the transmitted body bytes.")
    if first.signature_count < 1 or second.signature_count < 1:
        raise AssertionError("Webhook attempt did not include a signature.")
    if first.response_body_persisted or second.response_body_persisted:
        raise AssertionError("Webhook receiver body was persisted by default.")
    return ScenarioObservation(
        "Webhook retries signed the exact body under one stable message identity.",
        {
            "message_id": first.message_id,
            "attempts": 2,
            "signature_count": first.signature_count,
            "response_body_persisted": False,
        },
    )


async def webhook_ssrf_matrix(driver: BoundaryDriver) -> ScenarioObservation:
    facet: WebhookFacet = _require(driver, WebhookFacet, Capability.WEBHOOKS.value)
    blocked = (
        "127.0.0.1",
        "169.254.169.254",
        "10.0.0.1",
        "::1",
        "::ffff:127.0.0.1",
    )
    rejected = 0
    for index, address in enumerate(blocked, start=1):
        try:
            await facet.deliver_webhook(
                message_id=f"msg_blocked_{index}",
                body=b"{}",
                endpoint_url="https://blocked.example/hooks",
                resolved_addresses=(address,),
                attempt_no=1,
            )
        except ConformanceAccessDenied:
            rejected += 1
    if rejected != len(blocked):
        raise AssertionError("Webhook endpoint accepted a forbidden resolved address.")
    return ScenarioObservation(
        "Webhook delivery rejected private, metadata, loopback, and mapped addresses.",
        {"rejected_addresses": rejected},
    )


async def executor_handoff_boundary(driver: BoundaryDriver) -> ScenarioObservation:
    facet: ExternalExecutorFacet = _require(
        driver,
        ExternalExecutorFacet,
        Capability.EXTERNAL_EXECUTOR.value,
    )
    origin = principal(scopes=frozenset({"invoices:read"}))
    delivery_id = UUID("44444444-4444-4444-8444-444444444444")
    attempt_id = UUID("55555555-5555-4555-8555-555555555555")
    enqueued = await facet.enqueue_handoff(
        principal=origin,
        delivery_id=delivery_id,
        attempt_id=attempt_id,
    )
    if enqueued.terminal or enqueued.status != "enqueued":
        raise AssertionError("Broker acknowledgement was treated as terminal execution.")
    if (
        enqueued.tenant_id != origin.tenant_id
        or enqueued.subject_id != origin.subject_id
        or enqueued.scopes != origin.scopes
    ):
        raise AssertionError("Executor handoff lost or changed the originating principal.")
    completed = await facet.execute_handoff(
        handoff_id=enqueued.handoff_id,
        worker_id="worker:one",
    )
    duplicate = await facet.execute_handoff(
        handoff_id=enqueued.handoff_id,
        worker_id="worker:duplicate",
    )
    if not completed.terminal or completed.status != "succeeded":
        raise AssertionError("Worker completion did not finalize the durable handoff.")
    if duplicate.execution_count != 1 or completed.execution_count != 1:
        raise AssertionError("Duplicate broker delivery executed the handler more than once.")
    if duplicate.task_id != enqueued.task_id or duplicate.handoff_id != enqueued.handoff_id:
        raise AssertionError("Executor handoff identity changed across worker delivery.")
    return ScenarioObservation(
        "External enqueue remained non-terminal and duplicate execution was fenced.",
        {
            "handoff_id": enqueued.handoff_id,
            "task_id": enqueued.task_id,
            "execution_count": duplicate.execution_count,
        },
    )


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "atomicity.commit",
        Invariant.ATOMIC_INTENT,
        Capability.TRANSACTIONAL_EFFECTS,
        "critical",
        5.0,
        atomic_commit,
        "Commit application state, event, and original delivery intents in one transaction.",
    ),
    Scenario(
        "atomicity.rollback",
        Invariant.ATOMIC_INTENT,
        Capability.TRANSACTIONAL_EFFECTS,
        "critical",
        5.0,
        atomic_rollback,
        "Ensure rollback removes both business state and all effect intents.",
    ),
    Scenario(
        "isolation.cross_tenant",
        Invariant.TENANT_CONTINUITY,
        Capability.TENANT_ISOLATION,
        "critical",
        5.0,
        cross_tenant_denial,
        "Default-deny every cross-tenant read and write path.",
    ),
    Scenario(
        "authority.snapshot_attenuation",
        Invariant.AUTHORITY_PROVENANCE,
        Capability.AUTHORIZATION,
        "critical",
        5.0,
        authority_snapshot,
        "Intersect origin scopes with route allowance and record snapshot provenance.",
    ),
    Scenario(
        "authority.revalidation_ceiling",
        Invariant.AUTHORITY_PROVENANCE,
        Capability.AUTHORIZATION,
        "critical",
        5.0,
        authority_revalidate,
        "Intersect current authority with the immutable origin ceiling and route allowance.",
    ),
    Scenario(
        "delivery.retry_identity",
        Invariant.STABLE_RETRY_IDENTITY,
        Capability.DELIVERY_LEASES,
        "error",
        5.0,
        stable_retry_identity,
        "Reuse delivery/message identity across automatic retries and allocate new attempt IDs.",
    ),
    Scenario(
        "delivery.independent_fanout",
        Invariant.INDEPENDENT_FANOUT,
        Capability.TRANSACTIONAL_EFFECTS,
        "error",
        5.0,
        independent_fanout,
        "Track each destination through an independent delivery state machine.",
    ),
    Scenario(
        "lineage.correlation_causation",
        Invariant.CAUSAL_LINEAGE,
        Capability.TRANSACTIONAL_EFFECTS,
        "error",
        5.0,
        causal_lineage,
        "Preserve explicit event, delivery, correlation, and causation identities.",
    ),
    Scenario(
        "replay.accountable_identity",
        Invariant.REPLAY_ACCOUNTABILITY,
        Capability.DELIVERY_LEASES,
        "error",
        5.0,
        replay_accountability,
        "Create a new linked delivery for replay without mutating terminal history.",
    ),
    Scenario(
        "lease.stale_finalization",
        Invariant.LEASE_FENCING,
        Capability.DELIVERY_LEASES,
        "critical",
        5.0,
        lease_fencing,
        "Fence every finalization with the exact active lease or execution token.",
    ),
    Scenario(
        "lifecycle.context_cleanup",
        Invariant.CONTEXT_CLEANUP,
        Capability.CONTEXT_LIFECYCLE,
        "critical",
        5.0,
        context_cleanup,
        "Reset principal and dependency context in a finally block after every attempt.",
    ),
    Scenario(
        "security.secret_minimization",
        Invariant.SECRET_MINIMIZATION,
        None,
        "critical",
        5.0,
        secret_minimization,
        "Exclude raw credentials and secret values from public evidence and reports.",
    ),
    Scenario(
        "idempotency.concurrent_duplicate",
        Invariant.COMMAND_IDENTITY,
        Capability.COMMAND_IDEMPOTENCY,
        "critical",
        5.0,
        command_concurrency,
        "Serialize the complete command identity and replay one committed result.",
    ),
    Scenario(
        "idempotency.fingerprint_conflict",
        Invariant.COMMAND_IDENTITY,
        Capability.COMMAND_IDEMPOTENCY,
        "critical",
        5.0,
        command_conflict,
        "Reject key reuse when the immutable request fingerprint differs.",
    ),
    Scenario(
        "delegation.exact_target",
        Invariant.DELEGATION_BINDING,
        Capability.DELEGATION,
        "critical",
        5.0,
        delegation_exact_target,
        "Bind delegated credentials to exact audience, method, path, tenant, and scopes.",
    ),
    Scenario(
        "delegation.rejection_matrix",
        Invariant.DELEGATION_BINDING,
        Capability.DELEGATION,
        "critical",
        5.0,
        delegation_rejection_matrix,
        "Reject every audience or target mismatch without forwarding the origin credential.",
    ),
    Scenario(
        "webhook.signed_retry",
        Invariant.WEBHOOK_BOUNDARY,
        Capability.WEBHOOKS,
        "critical",
        5.0,
        webhook_signed_retry,
        "Sign the exact sent bytes, retain message identity, and discard receiver bodies.",
    ),
    Scenario(
        "webhook.ssrf_matrix",
        Invariant.WEBHOOK_BOUNDARY,
        Capability.WEBHOOKS,
        "critical",
        5.0,
        webhook_ssrf_matrix,
        "Resolve and reject every forbidden destination address at delivery time.",
    ),
    Scenario(
        "executor.durable_handoff",
        Invariant.EXECUTOR_HANDOFF,
        Capability.EXTERNAL_EXECUTOR,
        "critical",
        5.0,
        executor_handoff_boundary,
        "Keep enqueue non-terminal and fence duplicate worker execution.",
    ),
)

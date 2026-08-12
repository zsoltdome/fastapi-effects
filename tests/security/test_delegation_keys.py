from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fastapi_mergen import Principal
from fastapi_mergen.delegation.audit import DelegationAuditEvent, DelegationAuditOutcome
from fastapi_mergen.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_mergen.delegation.signing import DelegationIssuer, DelegationVerifier
from fastapi_mergen.errors import AuthorizationDenied, MergenConfigurationError

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


class MutableClock:
    def __init__(self) -> None:
        self.value = NOW

    def now(self) -> datetime:
        return self.value


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[DelegationAuditEvent] = []

    def record(self, event: DelegationAuditEvent) -> None:
        self.events.append(event)


def _verify(verifier: DelegationVerifier, token: str) -> None:
    verifier.verify(
        token=token,
        audience="billing-api",
        method="POST",
        path="/v1/pay",
        required_scopes=frozenset({"billing:write"}),
    )


def test_rotation_overlap_and_immediate_revocation_are_audited() -> None:
    clock = MutableClock()
    audit = RecordingAudit()
    keys = InMemoryKeyRing(
        (SigningKey("key-v1", b"a" * 32),),
        maximum_overlap=timedelta(minutes=5),
        audit=audit,
    )
    issuer = DelegationIssuer(issuer="gateway", keys=keys, clock=clock, audit=audit)
    verifier = DelegationVerifier(
        issuer="gateway",
        keys=keys,
        clock=clock,
        allowed_scopes=frozenset({"billing:write"}),
        audit=audit,
    )
    principal = Principal(
        tenant_id=UUID("10000000-0000-0000-0000-000000000012"),
        subject_id="user:alice",
        actor_id="operator:seven",
        client_id="mcp:billing",
        scopes=frozenset({"billing:write"}),
        issued_at=NOW,
    )
    old_token = issuer.mint(
        principal=principal,
        audience="billing-api",
        method="POST",
        path="/v1/pay",
        scopes=principal.scopes,
        ttl=timedelta(minutes=2),
        trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    keys.rotate(
        SigningKey("key-v2", b"b" * 32),
        now=NOW,
        overlap=timedelta(minutes=3),
    )
    _verify(verifier, old_token)
    new_token = issuer.mint(
        principal=principal,
        audience="billing-api",
        method="POST",
        path="/v1/pay",
        scopes=principal.scopes,
        ttl=timedelta(minutes=2),
    )
    assert "key-v2" not in new_token
    keys.revoke("key-v2", now=NOW)
    with pytest.raises(AuthorizationDenied):
        _verify(verifier, new_token)
    with pytest.raises(MergenConfigurationError, match="active key"):
        issuer.mint(
            principal=principal,
            audience="billing-api",
            method="POST",
            path="/v1/pay",
            scopes=principal.scopes,
            ttl=timedelta(minutes=1),
        )
    clock.value = NOW + timedelta(minutes=3)
    with pytest.raises(AuthorizationDenied):
        _verify(verifier, old_token)

    outcomes = {event.outcome for event in audit.events}
    assert DelegationAuditOutcome.KEY_ROTATED in outcomes
    assert DelegationAuditOutcome.KEY_REVOKED in outcomes
    assert DelegationAuditOutcome.ISSUED in outcomes
    assert DelegationAuditOutcome.ALLOWED in outcomes
    assert DelegationAuditOutcome.DENIED in outcomes
    evidence = repr(audit.events)
    assert old_token not in evidence
    assert new_token not in evidence
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in evidence
    assert "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" not in evidence


def test_rotation_rejects_excessive_overlap() -> None:
    keys = InMemoryKeyRing(
        (SigningKey("key-v1", b"a" * 32),),
        maximum_overlap=timedelta(minutes=5),
    )
    with pytest.raises(MergenConfigurationError, match="overlap"):
        keys.rotate(
            SigningKey("key-v2", b"b" * 32),
            now=NOW,
            overlap=timedelta(minutes=6),
        )

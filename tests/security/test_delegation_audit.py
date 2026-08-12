from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fastapi_mergen import Principal
from fastapi_mergen.delegation.audit import DelegationAuditEvent
from fastapi_mergen.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_mergen.delegation.signing import DelegationIssuer, DelegationVerifier
from fastapi_mergen.errors import AuthorizationDenied


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 30, 12, tzinfo=UTC)


class Recorder:
    def __init__(self) -> None:
        self.events: list[DelegationAuditEvent] = []

    def record(self, event: DelegationAuditEvent) -> None:
        self.events.append(event)


def test_audit_retains_approved_provenance_without_credential_material() -> None:
    audit = Recorder()
    keys = InMemoryKeyRing((SigningKey("audit-key", b"secret-canary-" * 3),))
    issuer = DelegationIssuer(issuer="gateway", keys=keys, clock=FixedClock(), audit=audit)
    verifier = DelegationVerifier(issuer="gateway", keys=keys, clock=FixedClock(), audit=audit)
    principal = Principal(
        tenant_id=uuid4(),
        subject_id="user:alice",
        actor_id="operator:one",
        client_id="mcp:billing",
        scopes=frozenset({"billing:read"}),
        issued_at=FixedClock().now(),
    )
    token = issuer.mint(
        principal=principal,
        audience="billing-api",
        method="GET",
        path="/v1/invoices/42",
        scopes=principal.scopes,
        ttl=timedelta(minutes=1),
    )
    verifier.verify(
        token=token,
        audience="billing-api",
        method="GET",
        path="/v1/invoices/42",
        required_scopes=principal.scopes,
    )
    with pytest.raises(AuthorizationDenied):
        verifier.verify(
            token=token,
            audience="other-api",
            method="GET",
            path="/v1/invoices/42",
            required_scopes=principal.scopes,
        )
    serialized = repr(audit.events)
    assert len(audit.events) == 3
    assert principal.subject_id in serialized
    assert str(principal.tenant_id) in serialized
    assert "target:" in serialized
    assert token not in serialized
    assert "secret-canary" not in serialized
    assert "/v1/invoices/42" not in serialized

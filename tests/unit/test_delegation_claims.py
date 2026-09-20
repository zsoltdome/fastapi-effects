from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fastapi_effects import Principal
from fastapi_effects.delegation.encoding import claims_bytes
from fastapi_effects.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_effects.delegation.models import DelegationClaims
from fastapi_effects.delegation.signing import DelegationIssuer, DelegationVerifier
from fastapi_effects.errors import AuthorizationDenied, FastAPIEffectsConfigurationError

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
TENANT = UUID("11111111-1111-4111-8111-111111111111")


class FixedClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FixedUUIDs:
    def new_uuid(self) -> UUID:
        return UUID("22222222-2222-4222-8222-222222222222")


def _services() -> tuple[DelegationIssuer, DelegationVerifier, FixedClock]:
    clock = FixedClock()
    keys = InMemoryKeyRing((SigningKey("delegation-v1", b"k" * 32),))
    return (
        DelegationIssuer(
            issuer="issuer.example",
            keys=keys,
            clock=clock,
            uuid_source=FixedUUIDs(),
        ),
        DelegationVerifier(issuer="issuer.example", keys=keys, clock=clock),
        clock,
    )


def test_delegation_claims_encode_and_verify_deterministically() -> None:
    issuer, verifier, _clock = _services()
    principal = Principal(
        tenant_id=TENANT,
        subject_id="user:42",
        actor_id="operator:7",
        client_id="mcp:billing",
        scopes=frozenset({"billing:read", "billing:write"}),
        issued_at=NOW,
    )
    token = issuer.mint(
        principal=principal,
        audience="billing-api",
        method="POST",
        path="/v1/invoices/42/pay",
        scopes=frozenset({"billing:write"}),
        ttl=timedelta(minutes=2),
    )
    claims = verifier.verify(
        token=token,
        audience="billing-api",
        method="POST",
        path="/v1/invoices/42/pay",
        required_scopes=frozenset({"billing:write"}),
    )
    assert claims.tenant_id == TENANT
    assert claims.scopes == ("billing:write",)
    assert claims_bytes(claims) == claims_bytes(DelegationClaims.from_dict(claims.to_dict()))
    assert "kkkk" not in repr(issuer)


@pytest.mark.parametrize(
    ("audience", "method", "path", "scopes"),
    [
        ("other-api", "POST", "/v1/invoices/42/pay", frozenset({"billing:write"})),
        ("billing-api", "GET", "/v1/invoices/42/pay", frozenset({"billing:write"})),
        ("billing-api", "POST", "/v1/invoices/43/pay", frozenset({"billing:write"})),
        ("billing-api", "POST", "/v1/invoices/42/pay", frozenset({"admin"})),
    ],
)
def test_delegation_verification_is_exact(
    audience: str,
    method: str,
    path: str,
    scopes: frozenset[str],
) -> None:
    issuer, verifier, _clock = _services()
    principal = Principal(
        tenant_id=TENANT,
        subject_id="user:42",
        scopes=frozenset({"billing:write"}),
        issued_at=NOW,
    )
    token = issuer.mint(
        principal=principal,
        audience="billing-api",
        method="POST",
        path="/v1/invoices/42/pay",
        scopes=principal.scopes,
        ttl=timedelta(minutes=2),
    )
    with pytest.raises(AuthorizationDenied, match="rejected"):
        verifier.verify(
            token=token,
            audience=audience,
            method=method,
            path=path,
            required_scopes=scopes,
        )


def test_delegation_rejects_expiry_tamper_and_scope_expansion() -> None:
    issuer, verifier, clock = _services()
    principal = Principal(
        tenant_id=TENANT,
        subject_id="user:42",
        scopes=frozenset({"billing:write"}),
        issued_at=NOW,
    )
    with pytest.raises(FastAPIEffectsConfigurationError, match="exceed"):
        issuer.mint(
            principal=principal,
            audience="billing-api",
            method="POST",
            path="/pay",
            scopes=frozenset({"admin"}),
            ttl=timedelta(minutes=1),
        )
    token = issuer.mint(
        principal=principal,
        audience="billing-api",
        method="POST",
        path="/pay",
        scopes=principal.scopes,
        ttl=timedelta(seconds=10),
    )
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(AuthorizationDenied):
        verifier.verify(
            token=tampered,
            audience="billing-api",
            method="POST",
            path="/pay",
            required_scopes=principal.scopes,
        )
    clock.value = NOW + timedelta(seconds=16)
    with pytest.raises(AuthorizationDenied):
        verifier.verify(
            token=token,
            audience="billing-api",
            method="POST",
            path="/pay",
            required_scopes=principal.scopes,
        )

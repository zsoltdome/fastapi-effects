from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from fastapi_mergen.core.principal import Principal
from fastapi_mergen.delegation.fastapi import (
    VerifiedDelegation,
    verified_delegation_dependency,
)
from fastapi_mergen.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_mergen.delegation.signing import DelegationIssuer, DelegationVerifier

pytestmark = pytest.mark.security

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.mark.asyncio
async def test_downstream_route_enforces_delegation_independent_of_discovery() -> None:
    keys = InMemoryKeyRing((SigningKey("route-key", b"r" * 32),))
    issuer = DelegationIssuer(issuer="gateway", keys=keys, clock=FixedClock())
    verifier = DelegationVerifier(
        issuer="gateway",
        keys=keys,
        clock=FixedClock(),
        allowed_scopes=frozenset({"billing:read", "billing:write"}),
    )
    dependency = verified_delegation_dependency(
        verifier,
        audience="billing-api",
        required_scopes=frozenset({"billing:write"}),
        route_allowed_scopes=frozenset({"billing:read", "billing:write"}),
    )
    app = FastAPI()

    @app.post("/v1/invoices/{invoice_id}/pay")
    async def pay(
        invoice_id: str,
        request: Request,
        delegation: VerifiedDelegation = Depends(dependency),
    ) -> dict[str, object]:
        assert request.state.mergen_delegation == delegation
        return {
            "invoice_id": invoice_id,
            "tenant_id": str(delegation.principal.tenant_id),
            "subject_id": delegation.principal.subject_id,
            "provenance": delegation.principal.credential_ref,
        }

    principal = Principal(
        tenant_id=UUID("10000000-0000-0000-0000-000000000012"),
        subject_id="user:alice",
        scopes=frozenset({"billing:write"}),
        issued_at=NOW,
    )
    token = issuer.mint(
        principal=principal,
        audience="billing-api",
        method="POST",
        path="/v1/invoices/42/pay",
        scopes=principal.scopes,
        ttl=timedelta(minutes=1),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://billing.example"
    ) as client:
        missing = await client.post("/v1/invoices/42/pay")
        wrong_path = await client.post("/v1/invoices/43/pay", headers={"Mergen-Delegation": token})
        allowed = await client.post("/v1/invoices/42/pay", headers={"Mergen-Delegation": token})
    assert missing.status_code == 401
    assert wrong_path.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["subject_id"] == "user:alice"
    assert allowed.json()["provenance"].startswith("delegation:")
    assert token not in repr(allowed.json())

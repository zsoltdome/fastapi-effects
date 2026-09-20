from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, Request
from fastmcp import Client, FastMCP
from httpx import ASGITransport, AsyncClient, Response

from fastapi_effects import Principal
from fastapi_effects.delegation.bridge import TrustedCallerMetadata
from fastapi_effects.delegation.fastapi import delegated_principal_dependency
from fastapi_effects.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_effects.delegation.signing import DelegationIssuer, DelegationVerifier
from fastapi_effects.integrations.fastmcp import FastMCPDelegationBridge

pytestmark = pytest.mark.security

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.mark.asyncio
async def test_real_fastmcp_tool_dispatches_only_internal_delegation() -> None:
    keys = InMemoryKeyRing((SigningKey("fastmcp-key", b"f" * 32),))
    issuer = DelegationIssuer(issuer="mcp-gateway", keys=keys, clock=FixedClock())
    verifier = DelegationVerifier(
        issuer="mcp-gateway",
        keys=keys,
        clock=FixedClock(),
        allowed_scopes=frozenset({"billing:write"}),
    )
    bridge = FastMCPDelegationBridge(
        issuer,
        allowed_scopes=frozenset({"billing:write"}),
    )
    caller = TrustedCallerMetadata(
        principal=Principal(
            tenant_id=UUID("10000000-0000-0000-0000-000000000012"),
            subject_id="user:alice",
            actor_id="operator:seven",
            client_id="fastmcp:billing",
            scopes=frozenset({"billing:write", "admin"}),
            issued_at=NOW,
        ),
        authentication_source="host.oauth",
    )
    downstream = FastAPI()
    observed_headers: dict[str, str] = {}
    dependency = delegated_principal_dependency(
        verifier,
        audience="billing-api",
        required_scopes=frozenset({"billing:write"}),
        route_allowed_scopes=frozenset({"billing:write"}),
    )

    @downstream.post("/v1/invoices/{invoice_id}/pay")
    async def pay(
        invoice_id: str,
        request: Request,
        principal: Principal = Depends(dependency),
    ) -> dict[str, str]:
        observed_headers.update(request.headers)
        return {
            "invoice_id": invoice_id,
            "tenant_id": str(principal.tenant_id),
            "subject_id": principal.subject_id,
        }

    mcp = FastMCP("FastAPIEffects delegation")

    @mcp.tool
    async def pay_invoice(invoice_id: str) -> dict[str, str]:
        """Pay one invoice through the separately authorized downstream API."""
        async with AsyncClient(
            transport=ASGITransport(app=downstream),
            base_url="https://billing.example",
        ) as downstream_client:
            response = cast(
                Response,
                await bridge.dispatch(
                    downstream_client,
                    caller=caller,
                    audience="billing-api",
                    method="POST",
                    path=f"/v1/invoices/{invoice_id}/pay",
                    requested_scopes=frozenset({"billing:write"}),
                    json_body={},
                    inbound_headers={
                        "Authorization": "Bearer origin-bearer-canary",
                        "Proxy-Authorization": "Basic origin-proxy-canary",
                        "Cookie": "session=origin-cookie-canary",
                        "X-Session-Token": "origin-session-canary",
                        "X-Api-Key": "origin-key-canary",
                        "X-Untrusted": "origin-arbitrary-canary",
                        "Traceparent": ("00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"),
                    },
                    trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ),
            )
        response.raise_for_status()
        return cast(dict[str, str], response.json())

    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert "pay_invoice" in {tool.name for tool in tools}
        result = await client.call_tool("pay_invoice", {"invoice_id": "42"})

    assert result.data == {
        "invoice_id": "42",
        "tenant_id": str(caller.principal.tenant_id),
        "subject_id": caller.principal.subject_id,
    }
    assert "fastapi-effects-delegation" in observed_headers
    assert "traceparent" in observed_headers
    serialized_headers = repr(observed_headers).lower()
    for forbidden in (
        "origin-bearer-canary",
        "origin-proxy-canary",
        "origin-cookie-canary",
        "origin-session-canary",
        "origin-key-canary",
        "origin-arbitrary-canary",
    ):
        assert forbidden not in serialized_headers
    assert "authorization" not in observed_headers
    assert "cookie" not in observed_headers

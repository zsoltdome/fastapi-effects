"""Build a FastMCP tool and separately authorized downstream FastAPI route."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from fastapi import Depends, FastAPI
from fastmcp import FastMCP
from httpx import AsyncClient, Response

from fastapi_effects.core.principal import Principal
from fastapi_effects.delegation.bridge import TrustedCallerMetadata
from fastapi_effects.delegation.fastapi import delegated_principal_dependency
from fastapi_effects.delegation.keys import InMemoryKeyRing, SigningKey
from fastapi_effects.delegation.signing import DelegationIssuer, DelegationVerifier
from fastapi_effects.integrations.fastmcp import FastMCPDelegationBridge


def build_apps(
    *,
    signing_key: bytes,
    caller_provider: Callable[[], TrustedCallerMetadata],
    downstream_client: AsyncClient,
) -> tuple[FastMCP, FastAPI]:
    """Wire applications; production keys and caller metadata come from the host."""
    keys = InMemoryKeyRing((SigningKey("delegation-v1", signing_key),))
    issuer = DelegationIssuer(issuer="mcp-gateway", keys=keys)
    verifier = DelegationVerifier(
        issuer="mcp-gateway",
        keys=keys,
        allowed_scopes=frozenset({"billing:write"}),
    )
    bridge = FastMCPDelegationBridge(
        issuer,
        allowed_scopes=frozenset({"billing:write"}),
    )
    downstream = FastAPI()
    require_billing_write = delegated_principal_dependency(
        verifier,
        audience="billing-api",
        required_scopes=frozenset({"billing:write"}),
        route_allowed_scopes=frozenset({"billing:write"}),
    )

    @downstream.post("/v1/invoices/{invoice_id}/pay")
    async def pay_invoice_api(
        invoice_id: str,
        principal: Principal = Depends(require_billing_write),
    ) -> dict[str, str]:
        return {
            "invoice_id": invoice_id,
            "tenant_id": str(principal.tenant_id),
            "subject_id": principal.subject_id,
        }

    mcp = FastMCP("Billing tools")

    @mcp.tool
    async def pay_invoice(invoice_id: str) -> dict[str, str]:
        """Pay one invoice as the host-authenticated caller."""
        response = cast(
            Response,
            await bridge.dispatch(
                downstream_client,
                caller=caller_provider(),
                audience="billing-api",
                method="POST",
                path=f"/v1/invoices/{invoice_id}/pay",
                requested_scopes=frozenset({"billing:write"}),
                json_body={},
            ),
        )
        response.raise_for_status()
        return cast(dict[str, str], response.json())

    return mcp, downstream


__all__ = ["build_apps"]

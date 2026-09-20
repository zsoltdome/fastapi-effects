"""Explicitly non-production principal provider for the bootable M1 example."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request, status

from fastapi_effects import Principal

DEMO_AUTHORIZATION = "Bearer milestone-one-demo"
DEMO_TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")


class DemoPrincipalProvider:
    """Map fixed demo credentials to one authorized tenant principal.

    This illustrates the protocol shape only. The tenant header is a candidate, not
    proof: it must match the tenant authorized for the fixed demo credential.
    Production integrations must authenticate through their own identity system and
    verify tenant membership before returning a Principal.
    """

    async def __call__(self, request: Request) -> Principal:
        if request.headers.get("authorization") != DEMO_AUTHORIZATION:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid demo token",
            )
        raw_tenant = request.headers.get("x-tenant-id")
        if raw_tenant is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing tenant")
        try:
            candidate_tenant = UUID(raw_tenant)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid tenant",
            ) from exc
        if candidate_tenant != DEMO_TENANT_ID:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="tenant is not authorized for demo token",
            )
        return Principal(
            tenant_id=DEMO_TENANT_ID,
            subject_id="demo-user",
            client_id="invoicing-example",
            scopes=frozenset({"invoices:read", "invoices:write"}),
        )

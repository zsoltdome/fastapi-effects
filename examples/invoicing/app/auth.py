"""Explicitly non-production principal provider for the bootable M1 example."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request, status

from fastapi_mergen import Principal


class DemoPrincipalProvider:
    """Map fixed demo credentials to one principal.

    This illustrates the protocol shape only. Production integrations must authenticate
    through their own identity system and verify tenant membership before returning a
    Principal.
    """

    async def __call__(self, request: Request) -> Principal:
        if request.headers.get("authorization") != "Bearer milestone-one-demo":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid demo token")
        raw_tenant = request.headers.get("x-tenant-id")
        if raw_tenant is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing tenant")
        try:
            tenant_id = UUID(raw_tenant)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid tenant") from exc
        return Principal(
            tenant_id=tenant_id,
            subject_id="demo-user",
            client_id="invoicing-example",
            scopes=frozenset({"invoices:read", "invoices:write"}),
        )

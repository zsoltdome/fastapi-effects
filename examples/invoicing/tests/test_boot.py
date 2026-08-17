from __future__ import annotations

from uuid import UUID

import pytest
from examples.invoicing.app.auth import DEMO_AUTHORIZATION, DEMO_TENANT_ID
from examples.invoicing.app.main import app
from examples.invoicing.app.mergen_config import mergen
from fastapi import status
from httpx import ASGITransport, AsyncClient

INVOICE_BODY = {
    "customer_id": "22222222-2222-4222-8222-222222222222",
    "amount": "10.50",
    "currency": "EUR",
}


def test_openapi_boots_without_database_or_optional_extras() -> None:
    schema = app.openapi()
    assert schema["info"]["title"] == "FastAPI-Mergen Invoicing Example"
    assert "/invoices" in schema["paths"]
    assert "/health" in schema["paths"]


@pytest.mark.asyncio
async def test_lifespan_freezes_routes_and_health_works() -> None:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client,
    ):
        response = await client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok", "milestone": "8"}
    assert mergen.frozen


@pytest.mark.asyncio
async def test_unauthenticated_request_fails_before_database_dependency() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/invoices", json=INVOICE_BODY)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_tenant_candidate_must_match_authorized_demo_tenant() -> None:
    other_tenant = UUID("33333333-3333-4333-8333-333333333333")
    assert other_tenant != DEMO_TENANT_ID
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/invoices",
            json=INVOICE_BODY,
            headers={
                "authorization": DEMO_AUTHORIZATION,
                "x-tenant-id": str(other_tenant),
            },
        )
    assert response.status_code == status.HTTP_403_FORBIDDEN

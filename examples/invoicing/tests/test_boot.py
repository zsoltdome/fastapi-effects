from __future__ import annotations

from fastapi.testclient import TestClient

from examples.invoicing.app.main import app
from examples.invoicing.app.mergen_config import mergen


def test_openapi_boots_without_database_or_optional_extras() -> None:
    schema = app.openapi()
    assert schema["info"]["title"] == "FastAPI-Mergen Invoicing Example"
    assert "/invoices" in schema["paths"]
    assert "/health" in schema["paths"]


def test_lifespan_freezes_routes_and_health_works() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "milestone": "1"}
    assert mergen.frozen

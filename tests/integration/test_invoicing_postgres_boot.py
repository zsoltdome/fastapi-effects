from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from examples.invoicing.app.db import get_async_session
from examples.invoicing.app.main import app
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_reference_app_boots_with_disposable_postgres(
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERGEN_EXAMPLE_DATABASE_URL", test_database.app_sqlalchemy_dsn)
    session_generator = get_async_session()
    session = await anext(session_generator)
    try:
        assert await session.scalar(text("SELECT 1")) == 1
        assert "/invoices" in app.openapi()["paths"]
    finally:
        await session_generator.aclose()
        os.environ.pop("MERGEN_EXAMPLE_DATABASE_URL", None)

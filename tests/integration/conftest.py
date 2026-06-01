"""PostgreSQL integration fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from tests.integration.postgres import TestDatabase, provision_test_database


@pytest.fixture(scope="session")
def postgres_admin_dsn() -> str:
    dsn = os.getenv("MERGEN_TEST_ADMIN_DSN")
    if not dsn:
        pytest.skip(
            "MERGEN_TEST_ADMIN_DSN is unset; start a compose profile and export the admin DSN."
        )
    return dsn


@pytest_asyncio.fixture
async def test_database(postgres_admin_dsn: str) -> AsyncIterator[TestDatabase]:
    async with provision_test_database(postgres_admin_dsn) as database:
        yield database

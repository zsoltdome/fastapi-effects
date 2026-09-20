"""Shared test configuration.

Mutable process-global state is forbidden. Each asynchronous test receives its own
loop scope through pytest-asyncio configuration.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from tests.integration.postgres import ProvisionedDatabase, provision_test_database


@pytest.fixture(scope="session")
def postgres_admin_dsn() -> str:
    dsn = os.getenv("FASTAPI_EFFECTS_TEST_ADMIN_DSN")
    if not dsn:
        pytest.skip(
            "FASTAPI_EFFECTS_TEST_ADMIN_DSN is unset; start a compose profile "
            "and export the admin DSN."
        )
    return dsn


@pytest_asyncio.fixture
async def test_database(postgres_admin_dsn: str) -> AsyncIterator[ProvisionedDatabase]:
    async with provision_test_database(postgres_admin_dsn) as database:
        yield database

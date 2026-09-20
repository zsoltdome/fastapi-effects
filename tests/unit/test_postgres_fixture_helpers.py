from __future__ import annotations

import pytest

from tests.integration.postgres import (
    _dsn_with_credentials,
    _quote_identifier,
    sqlalchemy_async_dsn,
)


def test_generated_identifier_validation() -> None:
    assert _quote_identifier("fastapi_effects_test_123") == '"fastapi_effects_test_123"'
    with pytest.raises(ValueError, match="unsafe"):
        _quote_identifier("unsafe; DROP ROLE postgres")


def test_dsn_builder_encodes_random_credentials() -> None:
    dsn = _dsn_with_credentials(
        "postgresql://admin:admin@127.0.0.1:55416/postgres?sslmode=disable",
        user="fastapi_effects_app_1",
        password="unsafe:/?#[]@!$&'()*+,;=",
        database="fastapi_effects_test_1",
    )
    assert dsn.startswith("postgresql://fastapi_effects_app_1:")
    assert "@127.0.0.1:55416/fastapi_effects_test_1?sslmode=disable" in dsn
    assert "unsafe:/" not in dsn
    assert sqlalchemy_async_dsn(dsn).startswith("postgresql+asyncpg://")

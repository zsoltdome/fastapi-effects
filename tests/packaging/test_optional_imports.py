from __future__ import annotations

import importlib.util

import pytest

from fastapi_mergen.errors import OptionalDependencyError


def test_base_import_has_no_http_client_side_effect() -> None:
    import fastapi_mergen

    assert fastapi_mergen.__version__


def test_missing_webhook_dependency_is_actionable() -> None:
    if all(
        importlib.util.find_spec(module) is not None
        for module in ("cryptography", "httpx", "standardwebhooks")
    ):
        pytest.skip("webhook extra is installed")
    with pytest.raises(OptionalDependencyError, match=r"fastapi-mergen\[webhooks\]"):
        __import__("fastapi_mergen.webhooks")

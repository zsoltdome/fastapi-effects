from __future__ import annotations

import importlib.util

import pytest

from fastapi_effects import _optional
from fastapi_effects.errors import OptionalDependencyError

pytestmark = pytest.mark.packaging


def test_base_import_has_no_http_client_side_effect() -> None:
    import fastapi_effects

    assert fastapi_effects.__version__


def test_missing_webhook_dependency_is_actionable() -> None:
    if all(importlib.util.find_spec(module) is not None for module in ("cryptography",)):
        pytest.skip("webhook extra is installed")
    with pytest.raises(OptionalDependencyError, match=r"fastapi-effects\[webhooks\]"):
        __import__("fastapi_effects.webhooks.secrets")


def test_missing_nested_optional_module_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_parent(module: str):
        if module == "missing_parent.child":
            raise ModuleNotFoundError("missing_parent")
        return importlib.util.find_spec(module)

    monkeypatch.setattr(_optional, "find_spec", missing_parent)
    with pytest.raises(OptionalDependencyError, match=r"fastapi-effects\[otel\]"):
        _optional.require_modules(
            feature="OpenTelemetry support",
            extra="otel",
            modules=("missing_parent.child",),
        )

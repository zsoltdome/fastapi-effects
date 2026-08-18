from __future__ import annotations

import importlib

import fastapi_mergen


def test_root_exports_are_intentional() -> None:
    assert fastapi_mergen.__all__ == [
        "AuthenticationRequired",
        "AuthorizationDenied",
        "AuthorizationExpired",
        "AuthorizationMode",
        "CommandConflict",
        "CommandInProgress",
        "DedupeConflict",
        "EffectContext",
        "Event",
        "LeaseLost",
        "Mergen",
        "MergenConfigurationError",
        "MergenError",
        "MergenUnitOfWork",
        "MilestoneNotImplementedError",
        "OptimisticConflict",
        "OptionalDependencyError",
        "PermanentDeliveryError",
        "Principal",
        "RetryPolicy",
        "RetryableDeliveryError",
        "SchemaRevisionMismatch",
        "__version__",
    ]
    assert not hasattr(fastapi_mergen, "Repository")
    assert not hasattr(fastapi_mergen, "SQLExpression")
    assert not hasattr(fastapi_mergen, "DBAPIConnection")
    assert not hasattr(fastapi_mergen, "HTTPClient")


def test_supported_namespace_exports_are_importable() -> None:
    modules = (
        "fastapi_mergen.conformance",
        "fastapi_mergen.delegation",
        "fastapi_mergen.executors",
        "fastapi_mergen.idempotency",
        "fastapi_mergen.observability",
        "fastapi_mergen.postgres",
        "fastapi_mergen.sqlalchemy",
        "fastapi_mergen.testing",
    )
    for module_name in modules:
        module = importlib.import_module(module_name)
        assert module.__all__
        for symbol in module.__all__:
            assert getattr(module, symbol) is not None

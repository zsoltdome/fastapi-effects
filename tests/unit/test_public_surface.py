from __future__ import annotations

import importlib

import fastapi_effects


def test_root_exports_are_intentional() -> None:
    assert fastapi_effects.__all__ == [
        "AuthenticationRequired",
        "AuthorizationDenied",
        "AuthorizationExpired",
        "AuthorizationMode",
        "CommandConflict",
        "CommandInProgress",
        "DedupeConflict",
        "EffectContext",
        "Event",
        "FastAPIEffects",
        "FastAPIEffectsConfigurationError",
        "FastAPIEffectsError",
        "FastAPIEffectsUnitOfWork",
        "LeaseLost",
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
    assert not hasattr(fastapi_effects, "Repository")
    assert not hasattr(fastapi_effects, "SQLExpression")
    assert not hasattr(fastapi_effects, "DBAPIConnection")
    assert not hasattr(fastapi_effects, "HTTPClient")


def test_supported_namespace_exports_are_importable() -> None:
    modules = (
        "fastapi_effects.conformance",
        "fastapi_effects.delegation",
        "fastapi_effects.executors",
        "fastapi_effects.idempotency",
        "fastapi_effects.observability",
        "fastapi_effects.postgres",
        "fastapi_effects.sqlalchemy",
        "fastapi_effects.testing",
    )
    for module_name in modules:
        module = importlib.import_module(module_name)
        assert module.__all__
        for symbol in module.__all__:
            assert getattr(module, symbol) is not None

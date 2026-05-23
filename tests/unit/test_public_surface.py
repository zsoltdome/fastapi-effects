from __future__ import annotations

import fastapi_mergen


def test_root_exports_are_intentional() -> None:
    assert fastapi_mergen.__all__ == [
        "AuthorizationDenied",
        "AuthorizationExpired",
        "AuthorizationMode",
        "DedupeConflict",
        "EffectContext",
        "Event",
        "LeaseLost",
        "Mergen",
        "MergenConfigurationError",
        "MergenError",
        "MergenUnitOfWork",
        "MilestoneNotImplementedError",
        "PermanentDeliveryError",
        "Principal",
        "RetryPolicy",
        "RetryableDeliveryError",
        "SchemaRevisionMismatch",
        "__version__",
    ]
    assert not hasattr(fastapi_mergen, "Repository")
    assert not hasattr(fastapi_mergen, "SQLExpression")

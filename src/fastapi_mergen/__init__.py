"""FastAPI-Mergen: principal-preserving transactional eventing."""

from fastapi_mergen._version import __version__
from fastapi_mergen.api import (
    AuthorizationMode,
    EffectContext,
    Event,
    Mergen,
    MergenUnitOfWork,
    Principal,
    RetryPolicy,
)
from fastapi_mergen.errors import (
    AuthorizationDenied,
    AuthorizationExpired,
    DedupeConflict,
    LeaseLost,
    MergenConfigurationError,
    MergenError,
    MilestoneNotImplementedError,
    PermanentDeliveryError,
    RetryableDeliveryError,
    SchemaRevisionMismatch,
)

__all__ = [
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

"""Public exception hierarchy for FastAPI Effects."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import ClassVar
from uuid import UUID

_STABLE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_MAX_SUMMARY_LENGTH = 512
_MAX_KEY_LENGTH = 512


class FastAPIEffectsError(Exception):
    """Base class for documented FastAPI Effects errors."""

    error_code: ClassVar[str] = "fastapi_effects.error"


class FastAPIEffectsConfigurationError(FastAPIEffectsError):
    """Raised when startup or integration configuration is invalid."""

    error_code = "fastapi_effects.configuration"


class OptionalDependencyError(FastAPIEffectsConfigurationError, ImportError):
    """Raised when an optional feature is imported without its extra."""

    error_code = "fastapi_effects.optional_dependency"

    def __init__(self, *, feature: str, extra: str, missing: tuple[str, ...]) -> None:
        self.feature = feature
        self.extra = extra
        self.missing = missing
        missing_display = ", ".join(missing)
        super().__init__(
            f"{feature} requires optional package(s): {missing_display}. "
            f'Install with: pip install "fastapi-effects[{extra}]"'
        )


class MilestoneNotImplementedError(FastAPIEffectsError, NotImplementedError):
    """Legacy pre-runtime failure type retained for import compatibility."""

    error_code = "fastapi_effects.legacy_not_implemented"


class AuthorizationExpired(FastAPIEffectsError):
    """Raised when snapshotted authority exceeds its allowed age."""

    error_code = "fastapi_effects.authorization_expired"


class AuthorizationDenied(FastAPIEffectsError):
    """Raised when effective authority lacks a required capability."""

    error_code = "fastapi_effects.authorization_denied"


class AuthenticationRequired(FastAPIEffectsError):
    """Raised when a command boundary has no authenticated principal."""

    error_code = "fastapi_effects.authentication_required"


class RetryableDeliveryError(FastAPIEffectsError):
    """Classify an execution failure as retryable under immutable policy."""

    error_code = "fastapi_effects.delivery_retryable"

    def __init__(
        self,
        *,
        code: str,
        summary: str,
        retry_after: timedelta | None = None,
    ) -> None:
        self.code = _validate_stable_code("delivery error code", code)
        self.summary = _bounded_summary(summary)
        if retry_after is not None and retry_after < timedelta(0):
            raise FastAPIEffectsConfigurationError("Delivery Retry-After cannot be negative.")
        self.retry_after = retry_after
        super().__init__(f"Retryable delivery failure ({self.code}).")


class PermanentDeliveryError(FastAPIEffectsError):
    """Classify an execution failure as terminal."""

    error_code = "fastapi_effects.delivery_permanent"

    def __init__(self, *, code: str, summary: str) -> None:
        self.code = _validate_stable_code("delivery error code", code)
        self.summary = _bounded_summary(summary)
        super().__init__(f"Permanent delivery failure ({self.code}).")


class DedupeConflict(FastAPIEffectsError):
    """Report a dedupe-key collision without exposing payload content."""

    error_code = "fastapi_effects.dedupe_conflict"

    def __init__(self, *, namespace: str, key: str) -> None:
        self.namespace = _validate_stable_code("dedupe namespace", namespace)
        self.key = _validate_safe_key(key)
        super().__init__(f"Dedupe key conflicts in namespace {self.namespace!r}.")


class LeaseLost(FastAPIEffectsError):
    """Report a stale lease token without mutating current delivery state."""

    error_code = "fastapi_effects.lease_lost"

    def __init__(self, *, delivery_id: UUID) -> None:
        if not isinstance(delivery_id, UUID):
            raise FastAPIEffectsConfigurationError("LeaseLost delivery_id must be a UUID.")
        self.delivery_id = delivery_id
        super().__init__(f"Lease ownership was lost for delivery {delivery_id}.")


class OptimisticConflict(FastAPIEffectsError):
    """Report a stale mutable-control revision without exposing protected data."""

    error_code = "fastapi_effects.optimistic_conflict"

    def __init__(self, *, resource: str) -> None:
        self.resource = _validate_stable_code("conflicted resource", resource)
        super().__init__(f"The {self.resource} revision changed concurrently.")


class CommandConflict(FastAPIEffectsError):
    """Report an immutable idempotency identity mismatch without stored details."""

    error_code = "fastapi_effects.command_conflict"

    def __init__(self) -> None:
        super().__init__("Idempotency identity conflicts with an earlier command.")


class CommandInProgress(FastAPIEffectsError):
    """Report an unexpected durable in-progress command without disclosing identity."""

    error_code = "fastapi_effects.command_in_progress"

    def __init__(self) -> None:
        super().__init__("The idempotent command is still in progress.")


class SchemaRevisionMismatch(FastAPIEffectsError):
    """Report an unsupported durable schema or snapshot revision."""

    error_code = "fastapi_effects.schema_revision_mismatch"

    def __init__(self, *, component: str, expected: int, actual: int) -> None:
        self.component = _validate_stable_code("schema component", component)
        if not _is_non_negative_integer(expected) or not _is_non_negative_integer(actual):
            raise FastAPIEffectsConfigurationError(
                "Schema revisions must be non-negative integers."
            )
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Unsupported {self.component} revision: expected {expected}, received {actual}."
        )


def _validate_stable_code(name: str, value: object) -> str:
    if not isinstance(value, str) or not _STABLE_CODE_PATTERN.fullmatch(value):
        raise FastAPIEffectsConfigurationError(f"Invalid {name}.")
    return value


def _bounded_summary(value: object) -> str:
    if not isinstance(value, str):
        raise FastAPIEffectsConfigurationError("Delivery failure summary must be a string.")
    normalized = _CONTROL_CHARACTER_PATTERN.sub(" ", value)
    return normalized[:_MAX_SUMMARY_LENGTH]


def _validate_safe_key(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_KEY_LENGTH
        or _CONTROL_CHARACTER_PATTERN.search(value) is not None
    ):
        raise FastAPIEffectsConfigurationError("Invalid dedupe key.")
    return value


def _is_non_negative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

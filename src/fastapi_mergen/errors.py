"""Public exception hierarchy for FastAPI-Mergen."""

from __future__ import annotations

import re
from uuid import UUID

_STABLE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_MAX_SUMMARY_LENGTH = 512
_MAX_KEY_LENGTH = 512


class MergenError(Exception):
    """Base class for documented FastAPI-Mergen errors."""


class MergenConfigurationError(MergenError):
    """Raised when startup or integration configuration is invalid."""


class OptionalDependencyError(MergenConfigurationError, ImportError):
    """Raised when an optional feature is imported without its extra."""

    def __init__(self, *, feature: str, extra: str, missing: tuple[str, ...]) -> None:
        self.feature = feature
        self.extra = extra
        self.missing = missing
        missing_display = ", ".join(missing)
        super().__init__(
            f"{feature} requires optional package(s): {missing_display}. "
            f'Install with: pip install "fastapi-mergen[{extra}]"'
        )


class MilestoneNotImplementedError(MergenError, NotImplementedError):
    """Raised when the Milestone 1 API spike reaches Milestone 2 behavior."""


class AuthorizationExpired(MergenError):
    """Raised when snapshotted authority exceeds its allowed age."""


class AuthorizationDenied(MergenError):
    """Raised when effective authority lacks a required capability."""


class RetryableDeliveryError(MergenError):
    """Classify an execution failure as retryable under immutable policy."""

    def __init__(self, *, code: str, summary: str) -> None:
        self.code = _validate_stable_code("delivery error code", code)
        self.summary = _bounded_summary(summary)
        super().__init__(f"Retryable delivery failure ({self.code}).")


class PermanentDeliveryError(MergenError):
    """Classify an execution failure as terminal."""

    def __init__(self, *, code: str, summary: str) -> None:
        self.code = _validate_stable_code("delivery error code", code)
        self.summary = _bounded_summary(summary)
        super().__init__(f"Permanent delivery failure ({self.code}).")


class DedupeConflict(MergenError):
    """Report a dedupe-key collision without exposing payload content."""

    def __init__(self, *, namespace: str, key: str) -> None:
        self.namespace = _validate_stable_code("dedupe namespace", namespace)
        self.key = _validate_safe_key(key)
        super().__init__(f"Dedupe key conflicts in namespace {self.namespace!r}.")


class LeaseLost(MergenError):
    """Report a stale lease token without mutating current delivery state."""

    def __init__(self, *, delivery_id: UUID) -> None:
        if not isinstance(delivery_id, UUID):
            raise MergenConfigurationError("LeaseLost delivery_id must be a UUID.")
        self.delivery_id = delivery_id
        super().__init__(f"Lease ownership was lost for delivery {delivery_id}.")


class SchemaRevisionMismatch(MergenError):
    """Report an unsupported durable schema or snapshot revision."""

    def __init__(self, *, component: str, expected: int, actual: int) -> None:
        self.component = _validate_stable_code("schema component", component)
        if not _is_non_negative_integer(expected) or not _is_non_negative_integer(actual):
            raise MergenConfigurationError("Schema revisions must be non-negative integers.")
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Unsupported {self.component} revision: expected {expected}, received {actual}."
        )


def _validate_stable_code(name: str, value: object) -> str:
    if not isinstance(value, str) or not _STABLE_CODE_PATTERN.fullmatch(value):
        raise MergenConfigurationError(f"Invalid {name}.")
    return value


def _bounded_summary(value: object) -> str:
    if not isinstance(value, str):
        raise MergenConfigurationError("Delivery failure summary must be a string.")
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
        raise MergenConfigurationError("Invalid dedupe key.")
    return value


def _is_non_negative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

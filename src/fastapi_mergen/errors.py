"""Public exception hierarchy for FastAPI-Mergen."""

from __future__ import annotations

import re
from uuid import UUID

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def _bounded_text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        return "invalid"
    cleaned = _CONTROL_CHARACTERS.sub("?", value).strip()
    return cleaned[:maximum] or "unspecified"


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
        self.code = _bounded_text(code, maximum=128)
        self.summary = _bounded_text(summary, maximum=512)
        super().__init__(f"Retryable delivery failure ({self.code}).")


class PermanentDeliveryError(MergenError):
    """Classify an execution failure as terminal."""

    def __init__(self, *, code: str, summary: str) -> None:
        self.code = _bounded_text(code, maximum=128)
        self.summary = _bounded_text(summary, maximum=512)
        super().__init__(f"Permanent delivery failure ({self.code}).")


class DedupeConflict(MergenError):
    """Report a dedupe-key collision without exposing payload content."""

    def __init__(self, *, namespace: str, key: str) -> None:
        self.namespace = _bounded_text(namespace, maximum=128)
        self.key = _bounded_text(key, maximum=512)
        super().__init__(f"Dedupe key conflicts in namespace {self.namespace!r}.")


class LeaseLost(MergenError):
    """Report a stale lease token without mutating current delivery state."""

    def __init__(self, *, delivery_id: UUID) -> None:
        self.delivery_id = delivery_id
        super().__init__(f"Lease ownership was lost for delivery {delivery_id}.")


class SchemaRevisionMismatch(MergenError):
    """Report an unsupported durable schema or snapshot revision."""

    def __init__(self, *, component: str, expected: int, actual: int) -> None:
        self.component = _bounded_text(component, maximum=128)
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Unsupported {self.component} revision: expected {expected}, received {actual}."
        )

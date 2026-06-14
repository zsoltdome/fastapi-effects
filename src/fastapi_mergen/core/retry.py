"""Retry policy value for the public API spike."""

from __future__ import annotations

import math
from dataclasses import dataclass

from fastapi_mergen.errors import MergenConfigurationError


def _is_positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Versioned immutable retry settings snapshotted into a future delivery."""

    name: str
    version: int = 1
    max_attempts: int = 8
    maximum_elapsed_seconds: int = 86_400
    base_delay_seconds: float = 2.0
    maximum_delay_seconds: float = 900.0
    handler_timeout_seconds: float = 60.0
    lease_duration_seconds: float = 120.0
    jitter: str = "full"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or self.name != self.name.strip()
            or len(self.name) > 128
        ):
            raise MergenConfigurationError("Retry policy name must be trimmed and non-blank.")
        if not _is_positive_integer(self.version) or not _is_positive_integer(
            self.max_attempts
        ):
            raise MergenConfigurationError(
                "Retry policy version and max_attempts must be positive integers."
            )
        if not _is_positive_integer(self.maximum_elapsed_seconds):
            raise MergenConfigurationError(
                "Retry maximum elapsed time must be a positive integer."
            )

        base_delay = _finite_number(self.base_delay_seconds)
        maximum_delay = _finite_number(self.maximum_delay_seconds)
        handler_timeout = _finite_number(self.handler_timeout_seconds)
        lease_duration = _finite_number(self.lease_duration_seconds)
        if base_delay is None or maximum_delay is None:
            raise MergenConfigurationError("Retry delay bounds must be finite numbers.")
        if base_delay < 0 or maximum_delay < base_delay:
            raise MergenConfigurationError("Retry delay bounds are invalid.")
        if handler_timeout is None or lease_duration is None:
            raise MergenConfigurationError("Timeout and lease duration must be finite numbers.")
        if handler_timeout <= 0 or lease_duration <= 0:
            raise MergenConfigurationError("Timeout and lease duration must be positive.")
        if lease_duration <= handler_timeout:
            raise MergenConfigurationError("Lease duration must exceed the handler timeout.")
        if not isinstance(self.jitter, str) or self.jitter != "full":
            raise MergenConfigurationError("Milestone 1 permits only full-jitter retry policy.")

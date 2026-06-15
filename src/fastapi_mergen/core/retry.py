"""Retry policy value for the public API spike."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from fastapi_mergen.errors import MergenConfigurationError

_POLICY_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


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
        if not isinstance(self.name, str) or not _POLICY_NAME_PATTERN.fullmatch(self.name):
            raise MergenConfigurationError(
                "Retry policy name must be a lower-case stable key."
            )
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

        base_delay = _finite_number("base delay", self.base_delay_seconds)
        maximum_delay = _finite_number("maximum delay", self.maximum_delay_seconds)
        handler_timeout = _finite_number("handler timeout", self.handler_timeout_seconds)
        lease_duration = _finite_number("lease duration", self.lease_duration_seconds)
        if base_delay < 0 or maximum_delay < base_delay:
            raise MergenConfigurationError("Retry delay bounds are invalid.")
        if handler_timeout <= 0 or lease_duration <= 0:
            raise MergenConfigurationError("Timeout and lease duration must be positive.")
        if lease_duration <= handler_timeout:
            raise MergenConfigurationError("Lease duration must exceed the handler timeout.")
        if maximum_delay > self.maximum_elapsed_seconds:
            raise MergenConfigurationError(
                "Retry maximum delay must not exceed maximum elapsed time."
            )
        if handler_timeout > self.maximum_elapsed_seconds:
            raise MergenConfigurationError(
                "Handler timeout must not exceed maximum elapsed time."
            )
        if self.jitter != "full":
            raise MergenConfigurationError("Milestone 1 permits only full-jitter retry policy.")


def _is_positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MergenConfigurationError(f"Retry {name} must be numeric.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise MergenConfigurationError(f"Retry {name} must be finite.")
    return numeric

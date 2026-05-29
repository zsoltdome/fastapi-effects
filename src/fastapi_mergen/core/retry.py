"""Retry policy value for the public API spike."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi_mergen.errors import MergenConfigurationError


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
        if not self.name.strip() or self.name != self.name.strip() or len(self.name) > 128:
            raise MergenConfigurationError("Retry policy name must be trimmed and non-blank.")
        if self.version < 1 or self.max_attempts < 1:
            raise MergenConfigurationError("Retry policy version and max_attempts must be positive.")
        if self.maximum_elapsed_seconds <= 0:
            raise MergenConfigurationError("Retry maximum elapsed time must be positive.")
        if self.base_delay_seconds < 0 or self.maximum_delay_seconds < self.base_delay_seconds:
            raise MergenConfigurationError("Retry delay bounds are invalid.")
        if self.handler_timeout_seconds <= 0 or self.lease_duration_seconds <= 0:
            raise MergenConfigurationError("Timeout and lease duration must be positive.")
        if self.lease_duration_seconds <= self.handler_timeout_seconds:
            raise MergenConfigurationError("Lease duration must exceed the handler timeout.")
        if self.jitter != "full":
            raise MergenConfigurationError("Milestone 1 permits only full-jitter retry policy.")

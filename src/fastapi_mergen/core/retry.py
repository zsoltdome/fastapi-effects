"""Retry policy value for the public API spike."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

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
            raise MergenConfigurationError("Retry policy name must be a lower-case stable key.")
        if not _is_positive_integer(self.version) or not _is_positive_integer(self.max_attempts):
            raise MergenConfigurationError(
                "Retry policy version and max_attempts must be positive integers."
            )
        if not _is_positive_integer(self.maximum_elapsed_seconds):
            raise MergenConfigurationError("Retry maximum elapsed time must be a positive integer.")

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
            raise MergenConfigurationError("Handler timeout must not exceed maximum elapsed time.")
        if self.jitter != "full":
            raise MergenConfigurationError("The runtime supports only full-jitter retry policy.")

    def retry_delay(self, attempt_number: int, random_source: UniformRandom) -> timedelta:
        """Calculate deterministic full-jitter backoff after one failed attempt."""
        if not _is_positive_integer(attempt_number):
            raise MergenConfigurationError("Retry attempt number must be positive.")
        upper = min(
            float(self.maximum_delay_seconds),
            float(self.base_delay_seconds) * (2 ** max(0, attempt_number - 1)),
        )
        delay = random_source.uniform(0.0, upper)
        if not math.isfinite(delay) or delay < 0 or delay > upper:
            raise MergenConfigurationError("Random source returned an invalid retry delay.")
        return timedelta(seconds=delay)

    def permits_retry(
        self,
        *,
        attempt_number: int,
        first_attempt_at: datetime,
        now: datetime,
    ) -> bool:
        if not _is_positive_integer(attempt_number):
            raise MergenConfigurationError("Retry attempt number must be positive.")
        for value in (first_attempt_at, now):
            if value.tzinfo is None or value.utcoffset() is None:
                raise MergenConfigurationError("Retry times must be timezone-aware.")
        elapsed = (now - first_attempt_at).total_seconds()
        return attempt_number < self.max_attempts and elapsed < self.maximum_elapsed_seconds

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "max_attempts": self.max_attempts,
            "maximum_elapsed_seconds": self.maximum_elapsed_seconds,
            "base_delay_seconds": float(self.base_delay_seconds),
            "maximum_delay_seconds": float(self.maximum_delay_seconds),
            "handler_timeout_seconds": float(self.handler_timeout_seconds),
            "lease_duration_seconds": float(self.lease_duration_seconds),
            "jitter": self.jitter,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> RetryPolicy:
        try:
            return cls(
                name=_snapshot_str(value["name"]),
                version=_snapshot_int(value["version"]),
                max_attempts=_snapshot_int(value["max_attempts"]),
                maximum_elapsed_seconds=_snapshot_int(value["maximum_elapsed_seconds"]),
                base_delay_seconds=_snapshot_float(value["base_delay_seconds"]),
                maximum_delay_seconds=_snapshot_float(value["maximum_delay_seconds"]),
                handler_timeout_seconds=_snapshot_float(value["handler_timeout_seconds"]),
                lease_duration_seconds=_snapshot_float(value["lease_duration_seconds"]),
                jitter=_snapshot_str(value["jitter"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MergenConfigurationError("Retry policy snapshot is invalid.") from exc


class UniformRandom(Protocol):
    def uniform(self, lower: float, upper: float) -> float: ...


def _snapshot_str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _snapshot_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError
    return value


def _snapshot_float(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError
    return float(value)


def _is_positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MergenConfigurationError(f"Retry {name} must be numeric.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise MergenConfigurationError(f"Retry {name} must be finite.")
    return numeric


def delivery_deadline(*, policy: RetryPolicy, created_at: datetime) -> datetime:
    """Return the immutable latest-finish horizon for one delivery."""

    _aware_time("delivery creation", created_at)
    return created_at + timedelta(seconds=policy.maximum_elapsed_seconds)


def attempt_deadline(
    *,
    policy: RetryPolicy,
    delivery_created_at: datetime,
    attempt_started_at: datetime,
    lease_expires_at: datetime,
) -> datetime:
    """Return the earliest hard deadline applying to an active attempt."""

    for name, value in (
        ("delivery creation", delivery_created_at),
        ("attempt start", attempt_started_at),
        ("lease expiry", lease_expires_at),
    ):
        _aware_time(name, value)
    return min(
        delivery_deadline(policy=policy, created_at=delivery_created_at),
        attempt_started_at + timedelta(seconds=policy.handler_timeout_seconds),
        lease_expires_at,
    )


def remaining_attempt_seconds(
    *,
    policy: RetryPolicy,
    delivery_created_at: datetime,
    attempt_started_at: datetime,
    lease_expires_at: datetime,
    now: datetime,
    configured_limit_seconds: float | None = None,
) -> float:
    """Return a timeout duration derived from the immutable wall-clock bounds."""

    _aware_time("current", now)
    remaining = (
        attempt_deadline(
            policy=policy,
            delivery_created_at=delivery_created_at,
            attempt_started_at=attempt_started_at,
            lease_expires_at=lease_expires_at,
        )
        - now
    ).total_seconds()
    if configured_limit_seconds is not None:
        configured = _finite_number("configured attempt limit", configured_limit_seconds)
        if configured <= 0:
            raise MergenConfigurationError("Configured attempt limit must be positive.")
        remaining = min(remaining, configured)
    return max(0.0, remaining)


def _aware_time(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MergenConfigurationError(f"Retry {name} time must be timezone-aware.")


__all__ = [
    "RetryPolicy",
    "UniformRandom",
    "attempt_deadline",
    "delivery_deadline",
    "remaining_attempt_seconds",
]

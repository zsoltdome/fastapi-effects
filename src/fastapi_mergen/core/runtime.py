"""Safe production defaults for injectable runtime protocols."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SystemRandom:
    def __init__(self) -> None:
        self._random = secrets.SystemRandom()

    def uniform(self, lower: float, upper: float) -> float:
        return self._random.uniform(lower, upper)


__all__ = ["SystemClock", "SystemRandom"]

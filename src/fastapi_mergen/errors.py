"""Public exception hierarchy for FastAPI-Mergen."""

from __future__ import annotations


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

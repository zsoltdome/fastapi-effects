"""Explicit SQLAlchemy unit-of-work API spike."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.core.event import Event
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.errors import MergenConfigurationError, MilestoneNotImplementedError

_DEDUPE_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_MAX_DEDUPE_KEY_LENGTH = 512


@dataclass(slots=True)
class MergenUnitOfWork:
    """Milestone 1 shape of the explicit outer transaction boundary.

    Transaction ownership, tenant binding, and persistence intentionally begin in
    Milestone 2. Entering the context or emitting now fails before performing SQL.
    """

    session: AsyncSession
    principal: Principal

    def __post_init__(self) -> None:
        if not isinstance(self.principal, Principal):
            raise MergenConfigurationError("MergenUnitOfWork principal must be a Principal.")

    async def __aenter__(self) -> MergenUnitOfWork:
        raise MilestoneNotImplementedError(
            "MergenUnitOfWork transaction handling is frozen but not implemented until Milestone 2."
        )

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc_value, traceback
        return False

    async def emit(
        self,
        event: Event[Any],
        *,
        dedupe_namespace: str | None = None,
        dedupe_key: str | None = None,
    ) -> None:
        """Validate the frozen call shape, then fail before persistence or SQL."""
        if not isinstance(event, Event):
            raise MergenConfigurationError("emit() requires an Event instance.")
        if (dedupe_namespace is None) != (dedupe_key is None):
            raise MergenConfigurationError(
                "dedupe_namespace and dedupe_key must be provided together."
            )
        if dedupe_namespace is not None:
            if (
                not isinstance(dedupe_namespace, str)
                or not _DEDUPE_NAMESPACE_PATTERN.fullmatch(dedupe_namespace)
            ):
                raise MergenConfigurationError("Dedupe namespace is invalid.")
            if (
                not isinstance(dedupe_key, str)
                or not dedupe_key
                or dedupe_key != dedupe_key.strip()
                or len(dedupe_key) > _MAX_DEDUPE_KEY_LENGTH
                or _CONTROL_CHARACTER_PATTERN.search(dedupe_key) is not None
            ):
                raise MergenConfigurationError("Dedupe key is invalid.")
        raise MilestoneNotImplementedError(
            "Atomic event emission is frozen but not implemented until Milestone 2."
        )

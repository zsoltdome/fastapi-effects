"""Explicit SQLAlchemy unit-of-work API spike."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.core.event import Event
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.errors import MilestoneNotImplementedError


@dataclass(slots=True)
class MergenUnitOfWork:
    """Milestone 1 shape of the explicit outer transaction boundary.

    Transaction ownership, tenant binding, and persistence intentionally begin in
    Milestone 2. Entering the context or emitting now fails before performing SQL.
    """

    session: AsyncSession
    principal: Principal

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
        """Fail closed until atomic persistence exists in Milestone 2."""
        del event, dedupe_namespace, dedupe_key
        raise MilestoneNotImplementedError(
            "Atomic event emission is frozen but not implemented until Milestone 2."
        )

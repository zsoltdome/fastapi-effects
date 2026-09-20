"""Lazy SQLAlchemy integration surface without import cycles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi_effects.sqlalchemy.models import Base as Base
    from fastapi_effects.sqlalchemy.repository import RuntimeRepository as RuntimeRepository
    from fastapi_effects.sqlalchemy.uow import FastAPIEffectsUnitOfWork as FastAPIEffectsUnitOfWork


def __getattr__(name: str) -> Any:
    if name == "Base":
        from fastapi_effects.sqlalchemy.models import Base

        return Base
    if name == "RuntimeRepository":
        from fastapi_effects.sqlalchemy.repository import RuntimeRepository

        return RuntimeRepository
    if name == "FastAPIEffectsUnitOfWork":
        from fastapi_effects.sqlalchemy.uow import FastAPIEffectsUnitOfWork

        return FastAPIEffectsUnitOfWork
    raise AttributeError(name)


__all__ = ["Base", "FastAPIEffectsUnitOfWork", "RuntimeRepository"]

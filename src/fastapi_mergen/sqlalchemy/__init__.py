"""Lazy SQLAlchemy integration surface without import cycles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi_mergen.sqlalchemy.models import Base as Base
    from fastapi_mergen.sqlalchemy.repository import RuntimeRepository as RuntimeRepository
    from fastapi_mergen.sqlalchemy.uow import MergenUnitOfWork as MergenUnitOfWork


def __getattr__(name: str) -> Any:
    if name == "Base":
        from fastapi_mergen.sqlalchemy.models import Base

        return Base
    if name == "RuntimeRepository":
        from fastapi_mergen.sqlalchemy.repository import RuntimeRepository

        return RuntimeRepository
    if name == "MergenUnitOfWork":
        from fastapi_mergen.sqlalchemy.uow import MergenUnitOfWork

        return MergenUnitOfWork
    raise AttributeError(name)


__all__ = ["Base", "MergenUnitOfWork", "RuntimeRepository"]

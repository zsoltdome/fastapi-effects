"""Replaceable host-application protocols used by the public API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Protocol, TypeAlias, TypeVar

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from .policy import AuthorizationMode
from .principal import Principal

PayloadT = TypeVar("PayloadT")


class PrincipalProvider(Protocol):
    """Authenticate a request and return one authorized tenant principal."""

    async def __call__(self, request: Request) -> Principal: ...


class AuthorizationResolver(Protocol):
    """Resolve effective scopes without silently expanding origin authority."""

    async def resolve(
        self,
        principal: Principal,
        required_scopes: frozenset[str],
        mode: AuthorizationMode,
        service_policy: str | None,
    ) -> frozenset[str]: ...


class Clock(Protocol):
    """Return an aware current time for deterministic policy tests."""

    def now(self) -> datetime: ...


class RandomSource(Protocol):
    """Supply deterministic randomness to retry-policy calculations."""

    def uniform(self, lower: float, upper: float) -> float: ...


class HandlerSessionProvider(Protocol):
    """Create a fresh tenant-bound application session per handler attempt."""

    def __call__(self, principal: Principal) -> AbstractAsyncContextManager[AsyncSession]: ...


class EffectStore(Protocol):
    """Future transactional store boundary without exposing persistence internals."""

    @property
    def name(self) -> str: ...


HandlerCallable: TypeAlias = Callable[[Any], Awaitable[None]]
SessionDependency: TypeAlias = Callable[..., AsyncSession]

"""Replaceable host-application protocols used by the public API."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from .event import Event, EventRecord
from .policy import AuthorizationMode
from .principal import Principal
from .routing import RouteSpecification


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


class ServicePolicyRegistry(Protocol):
    """Resolve named service authority during startup configuration."""

    def capabilities_for(self, service_policy: str) -> Iterable[str] | None: ...


class Clock(Protocol):
    """Return an aware current time for deterministic policy tests."""

    def now(self) -> datetime: ...


class UUIDGenerator(Protocol):
    """Return opaque UUIDs without promising chronological ordering."""

    def new_uuid(self) -> UUID: ...


class RandomSource(Protocol):
    """Supply deterministic randomness to retry-policy calculations."""

    def uniform(self, lower: float, upper: float) -> float: ...


class HandlerSessionProvider(Protocol):
    """Create a fresh tenant-bound application session per handler attempt."""

    def __call__(self, principal: Principal) -> AbstractAsyncContextManager[AsyncSession]: ...


class EffectStore(Protocol):
    """Transactional effect store without exposing ORM rows publicly."""

    @property
    def name(self) -> str: ...

    async def publish(
        self,
        *,
        session: AsyncSession,
        principal: Principal,
        event: Event[object],
        routes: Sequence[RouteSpecification],
        clock: Clock,
        uuid_source: UUIDGenerator,
        dedupe_namespace: str | None,
        dedupe_key: str | None,
    ) -> EventRecord: ...


class EffectRouteProvider(Protocol):
    """Resolve transaction-local immutable destinations for one event."""

    async def routes_for(
        self,
        *,
        session: AsyncSession,
        principal: Principal,
        event: Event[object],
    ) -> Sequence[RouteSpecification]: ...

"""Explicit outer SQLAlchemy transaction ownership."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from contextvars import Token
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from fastapi_mergen.core.context import bind_principal, reset_principal
from fastapi_mergen.core.event import Event, EventRecord
from fastapi_mergen.core.identity import DedupeIdentity, UUIDSource
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.protocols import Clock, EffectRouteProvider, EffectStore, UUIDGenerator
from fastapi_mergen.core.routing import RouteSpecification
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.errors import MergenConfigurationError

_SESSION_MARKER = "fastapi_mergen.active_uow"


@dataclass(slots=True)
class MergenUnitOfWork:
    """Own one application transaction containing business and effect intent."""

    session: AsyncSession
    principal: Principal
    store: EffectStore | None = None
    routes: Sequence[RouteSpecification] = ()
    route_providers: Sequence[EffectRouteProvider] = ()
    clock: Clock = field(default_factory=SystemClock)
    uuid_source: UUIDGenerator = field(default_factory=UUIDSource)
    _transaction: AsyncSessionTransaction | None = field(default=None, init=False, repr=False)
    _principal_token: Token[Principal | None] | None = field(default=None, init=False, repr=False)
    _active: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.session, AsyncSession):
            raise MergenConfigurationError("MergenUnitOfWork session must be an AsyncSession.")
        if not isinstance(self.principal, Principal):
            raise MergenConfigurationError("MergenUnitOfWork principal must be a Principal.")
        self.routes = tuple(self.routes)
        self.route_providers = tuple(self.route_providers)

    @property
    def active(self) -> bool:
        return self._active

    async def __aenter__(self) -> MergenUnitOfWork:
        if self._active or self.session.info.get(_SESSION_MARKER) is not None:
            raise MergenConfigurationError("Nested Mergen unit of work is not allowed.")
        if self.session.in_transaction():
            raise MergenConfigurationError(
                "Mergen requires an idle session and owns the outer transaction."
            )

        transaction = self.session.begin()
        self._transaction = transaction
        try:
            await transaction.__aenter__()
            self.session.info[_SESSION_MARKER] = id(self)
            self._principal_token = bind_principal(self.principal)
            await self.session.execute(
                text("SELECT set_config('mergen.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(self.principal.tenant_id)},
            )
            await self.session.execute(
                text("SELECT set_config('mergen.subject_id', :subject_id, true)"),
                {"subject_id": self.principal.subject_id},
            )
            self._active = True
            return self
        except BaseException:
            exc_type, exc_value, traceback = sys.exc_info()
            await self._cleanup()
            await transaction.__aexit__(exc_type, exc_value, traceback)
            self._transaction = None
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        transaction = self._transaction
        if transaction is None:
            return
        try:
            await transaction.__aexit__(exc_type, exc_value, traceback)
        finally:
            await self._cleanup()
            self._transaction = None

    async def emit(
        self,
        event: Event[Any],
        *,
        dedupe_namespace: str | None = None,
        dedupe_key: str | None = None,
    ) -> EventRecord:
        """Persist event and original fanout inside this UoW's active transaction."""
        if not isinstance(event, Event):
            raise MergenConfigurationError("emit() requires an Event instance.")
        identity: DedupeIdentity | None = None
        if (dedupe_namespace is None) != (dedupe_key is None):
            raise MergenConfigurationError(
                "dedupe_namespace and dedupe_key must be provided together."
            )
        if dedupe_namespace is not None and dedupe_key is not None:
            identity = DedupeIdentity(namespace=dedupe_namespace, key=dedupe_key)
        if not self._active or self._transaction is None:
            raise MergenConfigurationError("emit() requires an active Mergen unit of work.")
        if self.store is None:
            raise MergenConfigurationError("No transactional effect store is configured.")
        matching_routes = list(_matching_routes(self.routes, event.type))
        for provider in self.route_providers:
            provided = await provider.routes_for(
                session=self.session,
                principal=self.principal,
                event=event,
            )
            matching_routes.extend(_matching_routes(tuple(provided), event.type))
        matching_routes = list(_unique_routes(matching_routes))
        return await self.store.publish(
            session=self.session,
            principal=self.principal,
            event=event,
            routes=tuple(matching_routes),
            clock=self.clock,
            uuid_source=self.uuid_source,
            dedupe_namespace=(None if identity is None else identity.namespace),
            dedupe_key=None if identity is None else identity.key,
        )

    async def _cleanup(self) -> None:
        self._active = False
        token = self._principal_token
        self._principal_token = None
        if token is not None:
            reset_principal(token)
        if self.session.info.get(_SESSION_MARKER) == id(self):
            self.session.info.pop(_SESSION_MARKER, None)


def _matching_routes(
    routes: Sequence[RouteSpecification],
    event_type: str,
) -> tuple[RouteSpecification, ...]:
    latest: dict[str, RouteSpecification] = {}
    for route in routes:
        if route.event_type != event_type:
            continue
        current = latest.get(route.route_key)
        if current is None or route.version > current.version:
            latest[route.route_key] = route
    return tuple(sorted(latest.values(), key=lambda item: (item.route_key, item.destination_key)))


def _unique_routes(
    routes: Sequence[RouteSpecification],
) -> tuple[RouteSpecification, ...]:
    unique: dict[tuple[str, int, str, str], RouteSpecification] = {}
    for route in routes:
        identity = (
            route.route_key,
            route.version,
            route.destination_kind,
            route.destination_key,
        )
        if identity in unique:
            raise MergenConfigurationError("Duplicate static and dynamic delivery route.")
        unique[identity] = route
    return tuple(sorted(unique.values(), key=lambda item: (item.route_key, item.destination_key)))


__all__ = ["MergenUnitOfWork"]

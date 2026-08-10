"""Explicit command-owned transaction and completion lifecycle."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from contextvars import Token
from dataclasses import dataclass, field
from datetime import timedelta
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction
from starlette.responses import Response

from fastapi_mergen.core.context import bind_principal, reset_principal
from fastapi_mergen.core.event import Event, EventRecord
from fastapi_mergen.core.identity import DedupeIdentity, UUIDSource
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.protocols import (
    Clock,
    EffectRouteProvider,
    EffectStore,
    UUIDGenerator,
)
from fastapi_mergen.core.routing import RouteSpecification
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.idempotency.fingerprint import RequestFingerprint
from fastapi_mergen.idempotency.models import CommandIdentity
from fastapi_mergen.idempotency.responses import CapturedResponse, capture_response
from fastapi_mergen.idempotency.store import CommandAcquisition, CommandStore

_SESSION_MARKER = "fastapi_mergen.active_uow"


@dataclass(slots=True)
class CommandContext:
    """Own the transaction containing a command claim and its business writes."""

    session: AsyncSession
    principal: Principal
    identity: CommandIdentity
    fingerprint: RequestFingerprint
    store: CommandStore = field(default_factory=CommandStore)
    clock: Clock = field(default_factory=SystemClock)
    effect_store: EffectStore | None = None
    routes: Sequence[RouteSpecification] = ()
    route_providers: Sequence[EffectRouteProvider] = ()
    uuid_source: UUIDGenerator = field(default_factory=UUIDSource)
    ttl: timedelta = timedelta(hours=24)
    _transaction: AsyncSessionTransaction | None = field(default=None, init=False, repr=False)
    _principal_token: Token[Principal | None] | None = field(default=None, init=False, repr=False)
    _acquisition: CommandAcquisition | None = field(default=None, init=False, repr=False)
    _completed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.session, AsyncSession):
            raise MergenConfigurationError("CommandContext session must be an AsyncSession.")
        if not isinstance(self.principal, Principal):
            raise MergenConfigurationError("CommandContext principal must be a Principal.")
        if not isinstance(self.identity, CommandIdentity):
            raise MergenConfigurationError("CommandContext identity is invalid.")
        if not isinstance(self.fingerprint, RequestFingerprint):
            raise MergenConfigurationError("CommandContext fingerprint is invalid.")
        self.routes = tuple(self.routes)
        self.route_providers = tuple(self.route_providers)

    @property
    def replayed(self) -> bool:
        return self._require_acquisition().replayed

    @property
    def response(self) -> CapturedResponse | None:
        return self._require_acquisition().response

    @property
    def generation(self) -> int:
        return self._require_acquisition().generation

    async def __aenter__(self) -> CommandContext:
        if self._transaction is not None or self.session.info.get(_SESSION_MARKER) is not None:
            raise MergenConfigurationError("Nested Mergen transaction ownership is not allowed.")
        if self.session.in_transaction():
            raise MergenConfigurationError(
                "CommandContext requires an idle session and owns the outer transaction."
            )
        if self.identity.tenant_id != self.principal.tenant_id:
            raise MergenConfigurationError("Command identity tenant does not match its principal.")
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
            self._acquisition = await self.store.acquire(
                self.session,
                principal=self.principal,
                identity=self.identity,
                fingerprint=self.fingerprint,
                now=self.clock.now(),
                ttl=self.ttl,
            )
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
        missing = exc_type is None and not self.replayed and not self._completed
        if missing:
            exc_value = MergenConfigurationError(
                "A new command requires complete() before successful context exit."
            )
            exc_type = type(exc_value)
            traceback = exc_value.__traceback__
        try:
            await transaction.__aexit__(exc_type, exc_value, traceback)
        finally:
            await self._cleanup()
            self._transaction = None
        if missing:
            if exc_value is None:  # Defensive: the missing-completion branch assigns it.
                raise RuntimeError("Command completion validation did not produce an error.")
            raise exc_value

    async def complete(self, response: CapturedResponse | Response) -> CapturedResponse:
        acquisition = self._require_acquisition()
        if acquisition.replayed:
            raise MergenConfigurationError("A replayed command cannot be completed again.")
        if self._completed:
            raise MergenConfigurationError("Command completion may only occur once.")
        captured = (
            response if isinstance(response, CapturedResponse) else capture_response(response)
        )
        await self.store.complete(
            self.session,
            acquisition=acquisition,
            tenant_id=self.principal.tenant_id,
            response=captured,
            now=self.clock.now(),
        )
        self._completed = True
        return captured

    async def emit(
        self,
        event: Event[object],
        *,
        dedupe_namespace: str | None = None,
        dedupe_key: str | None = None,
    ) -> EventRecord:
        """Persist effect intent inside the command-owned transaction."""
        acquisition = self._require_acquisition()
        if acquisition.replayed:
            raise MergenConfigurationError("A replayed command cannot emit new effect intent.")
        if self.effect_store is None:
            raise MergenConfigurationError("No transactional effect store is configured.")
        if (dedupe_namespace is None) != (dedupe_key is None):
            raise MergenConfigurationError(
                "dedupe_namespace and dedupe_key must be provided together."
            )
        identity = (
            None
            if dedupe_namespace is None or dedupe_key is None
            else DedupeIdentity(namespace=dedupe_namespace, key=dedupe_key)
        )
        matching_routes = list(_matching_routes(self.routes, event.type))
        for provider in self.route_providers:
            provided = await provider.routes_for(
                session=self.session,
                principal=self.principal,
                event=event,
            )
            matching_routes.extend(_matching_routes(tuple(provided), event.type))
        return await self.effect_store.publish(
            session=self.session,
            principal=self.principal,
            event=event,
            routes=_unique_routes(matching_routes),
            clock=self.clock,
            uuid_source=self.uuid_source,
            dedupe_namespace=None if identity is None else identity.namespace,
            dedupe_key=None if identity is None else identity.key,
        )

    def replay_response(self) -> Response:
        response = self.response
        if response is None:
            raise MergenConfigurationError("The command does not have a replay response.")
        return response.to_response(replayed=True)

    def _require_acquisition(self) -> CommandAcquisition:
        if self._transaction is None or self._acquisition is None:
            raise MergenConfigurationError("CommandContext is not active.")
        return self._acquisition

    async def _cleanup(self) -> None:
        token = self._principal_token
        self._principal_token = None
        if token is not None:
            reset_principal(token)
        if self.session.info.get(_SESSION_MARKER) == id(self):
            self.session.info.pop(_SESSION_MARKER, None)
        self._acquisition = None
        self._completed = False


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


__all__ = ["CommandContext"]

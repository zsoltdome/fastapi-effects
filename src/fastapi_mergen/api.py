"""Intentionally narrow public API for the Milestone 1 design spike."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, cast
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.core.event import Event
from fastapi_mergen.core.policy import AuthorizationMode
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.protocols import (
    AuthorizationResolver,
    Clock,
    EffectStore,
    HandlerSessionProvider,
    PrincipalProvider,
    RandomSource,
)
from fastapi_mergen.core.retry import RetryPolicy
from fastapi_mergen.core.routing import (
    HandlerRouteBuilder,
    RouteRegistry,
    RouteSpecification,
    validate_route_declaration,
)
from fastapi_mergen.errors import MergenConfigurationError, MilestoneNotImplementedError
from fastapi_mergen.sqlalchemy.uow import MergenUnitOfWork

PayloadT = TypeVar("PayloadT", covariant=True)
SessionDependency = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class EffectContext(Generic[PayloadT]):
    """Tenant and causal context supplied to one future handler attempt."""

    event: Event[PayloadT]
    principal: Principal
    delivery_id: UUID
    route_key: str
    route_version: int
    attempt_number: int
    _application_session_provider: HandlerSessionProvider | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def application_session(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Open a fresh tenant-bound app session, never the relay control session."""
        if self._application_session_provider is None:
            raise MilestoneNotImplementedError(
                "Handler application sessions are implemented in Milestone 2."
            )
        return self._application_session_provider(self.principal)


class Mergen:
    """Configure trusted principal ingress and exact future effect routes."""

    def __init__(
        self,
        *,
        principal_provider: PrincipalProvider,
        store: EffectStore | None = None,
        authorization_resolver: AuthorizationResolver | None = None,
        clock: Clock | None = None,
        random_source: RandomSource | None = None,
        handler_session_provider: HandlerSessionProvider | None = None,
    ) -> None:
        self._principal_provider = principal_provider
        self._store = store
        self._authorization_resolver = authorization_resolver
        self._clock = clock
        self._random_source = random_source
        self._handler_session_provider = handler_session_provider
        self._registry = RouteRegistry()

    @property
    def store_name(self) -> str | None:
        """Expose only the declared store identity, not persistence internals."""
        return None if self._store is None else self._store.name

    @property
    def routes(self) -> tuple[RouteSpecification, ...]:
        """Return immutable route declarations for diagnostics and tests."""
        return self._registry.specifications()

    @property
    def frozen(self) -> bool:
        """Report whether startup route registration is closed."""
        return self._registry.frozen

    def route(
        self,
        *,
        event_type: str,
        route_key: str,
        version: int = 1,
    ) -> HandlerRouteBuilder[Any]:
        """Declare one exact event route; wildcard matching is intentionally absent."""
        validate_route_declaration(
            event_type=event_type,
            route_key=route_key,
            version=version,
        )
        return HandlerRouteBuilder(
            registry=self._registry,
            event_type=event_type,
            route_key=route_key,
            version=version,
        )

    def handler(
        self,
        key: str,
        *,
        version: int = 1,
    ) -> Callable[
        [Callable[[EffectContext[Any]], Awaitable[None]]],
        Callable[[EffectContext[Any]], Awaitable[None]],
    ]:
        """Register an explicitly keyed handler without implying a task queue."""

        def decorator(
            function: Callable[[EffectContext[Any]], Awaitable[None]],
        ) -> Callable[[EffectContext[Any]], Awaitable[None]]:
            self._registry.register_handler(key=key, version=version, handler=function)
            return function

        return decorator

    def freeze(self) -> None:
        """Validate route references and make registration immutable."""
        self._registry.freeze()

    def matching_routes(self, event_type: str) -> tuple[RouteSpecification, ...]:
        """Return deterministic exact matches for API-spike evaluation."""
        return self._registry.matching(event_type)

    def uow_dependency(
        self,
        session_dependency: SessionDependency,
    ) -> Callable[..., Awaitable[MergenUnitOfWork]]:
        """Build a FastAPI dependency that resolves principal before UoW entry.

        The supplied session dependency owns session creation/finalization. This
        wrapper performs no application SQL and does not enter a transaction.
        """

        async def dependency(
            request: Request,
            session: AsyncSession = Depends(session_dependency),
        ) -> MergenUnitOfWork:
            principal = await self._principal_provider(request)
            if not isinstance(principal, Principal):
                raise MergenConfigurationError(
                    "Principal provider must return a validated Principal instance."
                )
            return MergenUnitOfWork(session=session, principal=principal)

        return dependency

    def providers_for_testing(
        self,
    ) -> tuple[
        AuthorizationResolver | None,
        Clock | None,
        RandomSource | None,
        HandlerSessionProvider | None,
    ]:
        """Expose replaceable protocol values without exposing implementation state."""
        return (
            self._authorization_resolver,
            self._clock,
            self._random_source,
            self._handler_session_provider,
        )


__all__ = [
    "AuthorizationMode",
    "EffectContext",
    "Event",
    "Mergen",
    "MergenUnitOfWork",
    "Principal",
    "RetryPolicy",
]

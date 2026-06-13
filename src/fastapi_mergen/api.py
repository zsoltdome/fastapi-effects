"""Intentionally narrow public API for the Milestone 1 design spike."""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar
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
    ServicePolicyRegistry,
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
_ROUTE_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


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

    def __post_init__(self) -> None:
        if not isinstance(self.event, Event):
            raise MergenConfigurationError("Effect context event must be an Event.")
        if not isinstance(self.principal, Principal):
            raise MergenConfigurationError("Effect context principal must be a Principal.")
        if not isinstance(self.delivery_id, UUID):
            raise MergenConfigurationError("Effect context delivery_id must be a UUID.")
        if not isinstance(self.route_key, str) or not _ROUTE_KEY.fullmatch(self.route_key):
            raise MergenConfigurationError("Effect context route_key is invalid.")
        if not _is_positive_integer(self.route_version):
            raise MergenConfigurationError("Effect context route_version must be positive.")
        if not _is_positive_integer(self.attempt_number):
            raise MergenConfigurationError("Effect context attempt_number must be positive.")

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
        service_policy_registry: ServicePolicyRegistry | None = None,
        clock: Clock | None = None,
        random_source: RandomSource | None = None,
        handler_session_provider: HandlerSessionProvider | None = None,
    ) -> None:
        if not _is_async_callable(principal_provider):
            raise MergenConfigurationError(
                "principal_provider must be an asynchronous callable."
            )
        if authorization_resolver is not None:
            resolve = getattr(authorization_resolver, "resolve", None)
            if resolve is None or not inspect.iscoroutinefunction(resolve):
                raise MergenConfigurationError(
                    "authorization_resolver.resolve must be asynchronous."
                )
        if service_policy_registry is not None:
            capabilities_for = getattr(service_policy_registry, "capabilities_for", None)
            if (
                capabilities_for is None
                or not callable(capabilities_for)
                or inspect.iscoroutinefunction(capabilities_for)
            ):
                raise MergenConfigurationError(
                    "service_policy_registry.capabilities_for must be synchronous."
                )
        self._principal_provider = principal_provider
        self._store = store
        self._authorization_resolver = authorization_resolver
        self._service_policy_registry = service_policy_registry
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
        """Resolve authorization configuration and close route registration."""
        if self._registry.frozen:
            return
        self._prepare_authorization_snapshots()
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
        ServicePolicyRegistry | None,
        Clock | None,
        RandomSource | None,
        HandlerSessionProvider | None,
    ]:
        """Expose replaceable protocol values without exposing implementation state."""
        return (
            self._authorization_resolver,
            self._service_policy_registry,
            self._clock,
            self._random_source,
            self._handler_session_provider,
        )

    def _prepare_authorization_snapshots(self) -> None:
        specifications = self._registry.specifications()
        if any(
            spec.authorization is AuthorizationMode.REVALIDATE
            for spec in specifications
        ) and self._authorization_resolver is None:
            raise MergenConfigurationError(
                "Revalidate routes require an authorization resolver."
            )

        service_routes = tuple(
            spec
            for spec in specifications
            if spec.authorization is AuthorizationMode.SERVICE_POLICY
        )
        if not service_routes:
            return
        registry = self._service_policy_registry
        if registry is None:
            raise MergenConfigurationError(
                "Service-policy routes require a service policy registry."
            )

        resolved: list[tuple[str, int, frozenset[str]]] = []
        for spec in service_routes:
            policy = spec.service_policy
            if policy is None:
                raise MergenConfigurationError("Service-policy route has no policy name.")
            try:
                capabilities = registry.capabilities_for(policy)
            except MergenConfigurationError:
                raise
            except Exception as exc:
                raise MergenConfigurationError(
                    "Service policy registry validation failed."
                ) from exc
            if capabilities is None:
                raise MergenConfigurationError("Named service policy is not registered.")
            resolved.append((spec.route_key, spec.version, capabilities))

        for route_key, version, capabilities in resolved:
            self._registry.snapshot_service_capabilities(
                route_key=route_key,
                version=version,
                capabilities=capabilities,
            )


def _is_async_callable(value: object) -> bool:
    if inspect.iscoroutinefunction(value):
        return True
    call = getattr(value, "__call__", None)
    return call is not None and inspect.iscoroutinefunction(call)


def _is_positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


__all__ = [
    "AuthorizationMode",
    "EffectContext",
    "Event",
    "Mergen",
    "MergenUnitOfWork",
    "Principal",
    "RetryPolicy",
]

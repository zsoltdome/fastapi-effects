"""Exact event route declarations for the Milestone 1 API spike."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from fastapi_mergen.core.policy import AuthorizationMode
from fastapi_mergen.core.retry import RetryPolicy
from fastapi_mergen.errors import MergenConfigurationError

if TYPE_CHECKING:
    from fastapi_mergen.api import EffectContext

PayloadT = TypeVar("PayloadT")
Handler = Callable[["EffectContext[Any]"], Awaitable[None]]
_ROUTE_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class RouteSpecification:
    """Serializable route data that a future delivery will snapshot."""

    event_type: str
    route_key: str
    version: int
    destination_kind: str
    destination_key: str
    required_scopes: tuple[str, ...]
    authorization: AuthorizationMode
    service_policy: str | None
    maximum_snapshot_age_seconds: int | None
    retry_policy: RetryPolicy


class RouteRegistry:
    """Register exact routes and handlers, then freeze before startup."""

    def __init__(self) -> None:
        self._routes: dict[tuple[str, int], RouteSpecification] = {}
        self._handlers: dict[tuple[str, int], Handler] = {}
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def register_handler(self, *, key: str, version: int, handler: Handler) -> None:
        self._require_mutable()
        _validate_key("Handler key", key)
        if version < 1:
            raise MergenConfigurationError("Handler version must be positive.")
        identity = (key, version)
        existing = self._handlers.get(identity)
        if existing is not None and existing is not handler:
            raise MergenConfigurationError(f"Duplicate handler registration: {key}@{version}.")
        self._handlers[identity] = handler

    def register_route(self, spec: RouteSpecification, handler: Handler) -> None:
        self._require_mutable()
        identity = (spec.route_key, spec.version)
        if identity in self._routes:
            raise MergenConfigurationError(
                f"Duplicate route registration: {spec.route_key}@{spec.version}."
            )
        prior_specs = [
            prior
            for (key, _version), prior in self._routes.items()
            if key == spec.route_key
        ]
        if any(prior.event_type != spec.event_type for prior in prior_specs):
            raise MergenConfigurationError(
                f"Route key {spec.route_key!r} cannot change its event type."
            )
        prior_versions = [prior.version for prior in prior_specs]
        if prior_versions and spec.version < max(prior_versions):
            raise MergenConfigurationError(
                f"Route version downgrade is not allowed for {spec.route_key!r}."
            )
        self.register_handler(key=spec.destination_key, version=spec.version, handler=handler)
        self._routes[identity] = spec

    def freeze(self) -> None:
        if self._frozen:
            return
        for spec in self._routes.values():
            identity = (spec.destination_key, spec.version)
            if identity not in self._handlers:
                raise MergenConfigurationError(
                    f"Route {spec.route_key}@{spec.version} has no registered handler."
                )
        self._frozen = True

    def matching(self, event_type: str) -> tuple[RouteSpecification, ...]:
        latest_by_key: dict[str, RouteSpecification] = {}
        for spec in self._routes.values():
            if spec.event_type != event_type:
                continue
            current = latest_by_key.get(spec.route_key)
            if current is None or spec.version > current.version:
                latest_by_key[spec.route_key] = spec
        return tuple(
            sorted(
                latest_by_key.values(),
                key=lambda spec: (spec.route_key, spec.destination_key),
            )
        )

    def specifications(self) -> tuple[RouteSpecification, ...]:
        return tuple(
            sorted(
                self._routes.values(),
                key=lambda spec: (spec.event_type, spec.route_key, spec.version),
            )
        )

    def _require_mutable(self) -> None:
        if self._frozen:
            raise MergenConfigurationError("Route registry is frozen; registration is closed.")


class HandlerRouteBuilder(Generic[PayloadT]):
    """Fluent declaration that records one future handler destination."""

    def __init__(
        self,
        *,
        registry: RouteRegistry,
        event_type: str,
        route_key: str,
        version: int,
    ) -> None:
        self._registry = registry
        self._event_type = event_type
        self._route_key = route_key
        self._version = version

    def to_handler(
        self,
        handler: Callable[["EffectContext[PayloadT]"], Awaitable[None]],
        *,
        required_scopes: Iterable[str] = (),
        authorization: AuthorizationMode | str = AuthorizationMode.REVALIDATE,
        service_policy: str | None = None,
        maximum_snapshot_age_seconds: int | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> Callable[["EffectContext[PayloadT]"], Awaitable[None]]:
        mode = AuthorizationMode.parse(authorization)
        scopes = _normalize_scopes(required_scopes)
        if mode is AuthorizationMode.SNAPSHOT:
            if maximum_snapshot_age_seconds is None or maximum_snapshot_age_seconds <= 0:
                raise MergenConfigurationError(
                    "Snapshot authorization requires a positive maximum snapshot age."
                )
            if service_policy is not None:
                raise MergenConfigurationError(
                    "Snapshot authorization cannot name a service policy."
                )
        elif mode is AuthorizationMode.REVALIDATE:
            if maximum_snapshot_age_seconds is not None or service_policy is not None:
                raise MergenConfigurationError(
                    "Revalidate authorization does not accept snapshot age or service policy."
                )
        else:
            if not service_policy or not service_policy.strip():
                raise MergenConfigurationError(
                    "Service-policy authorization requires a named service policy."
                )
            if maximum_snapshot_age_seconds is not None:
                raise MergenConfigurationError(
                    "Service-policy authorization does not accept snapshot maximum age."
                )

        policy = retry_policy or RetryPolicy(name="default-handler")
        spec = RouteSpecification(
            event_type=self._event_type,
            route_key=self._route_key,
            version=self._version,
            destination_kind="handler",
            destination_key=self._route_key,
            required_scopes=scopes,
            authorization=mode,
            service_policy=service_policy,
            maximum_snapshot_age_seconds=maximum_snapshot_age_seconds,
            retry_policy=policy,
        )
        self._registry.register_route(spec, cast(Handler, handler))
        return handler


def validate_route_declaration(*, event_type: str, route_key: str, version: int) -> None:
    from fastapi_mergen.core.event import Event

    Event(type=event_type, version=1, data=None)
    _validate_key("Route key", route_key)
    if version < 1:
        raise MergenConfigurationError("Route version must be positive.")


def _validate_key(name: str, value: str) -> None:
    if not _ROUTE_KEY.fullmatch(value):
        raise MergenConfigurationError(
            f"{name} must use lower-case letters, digits, dots, underscores, or hyphens."
        )


def _normalize_scopes(scopes: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(scopes)))
    if len(normalized) > 256 or any(not _SCOPE.fullmatch(scope) for scope in normalized):
        raise MergenConfigurationError("Route contains invalid required scopes.")
    return normalized

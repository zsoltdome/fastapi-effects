"""Exact event routes and immutable execution-policy snapshots."""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from fastapi_effects.core.policy import AuthorizationMode
from fastapi_effects.core.retry import RetryPolicy
from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.sqlalchemy.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from fastapi_effects.api import EffectContext

PayloadT = TypeVar("PayloadT")
Handler = Callable[["EffectContext[Any]"], Awaitable[None]]
RouteIdentity = tuple[str, int]
_ROUTE_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class RouteSpecification:
    """Serializable route data snapshotted into every original delivery."""

    event_type: str
    route_key: str
    version: int
    destination_kind: str
    destination_key: str
    required_scopes: tuple[str, ...]
    authorization: AuthorizationMode
    service_policy: str | None
    service_capabilities: tuple[str, ...] | None
    maximum_snapshot_age_seconds: int | None
    retry_policy: RetryPolicy
    destination_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_route_declaration(
            event_type=self.event_type,
            route_key=self.route_key,
            version=self.version,
        )
        _validate_key("Destination kind", self.destination_kind)
        _validate_key("Destination key", self.destination_key)
        normalized_scopes = _normalize_scopes(self.required_scopes)
        object.__setattr__(self, "required_scopes", normalized_scopes)
        if not isinstance(self.authorization, AuthorizationMode):
            raise FastAPIEffectsConfigurationError("Route authorization mode is invalid.")
        if self.service_policy is not None:
            _validate_key("Service policy", self.service_policy)
        if self.service_capabilities is not None:
            object.__setattr__(
                self,
                "service_capabilities",
                _normalize_scopes(self.service_capabilities),
            )
        if self.maximum_snapshot_age_seconds is not None and not _is_positive_integer(
            self.maximum_snapshot_age_seconds
        ):
            raise FastAPIEffectsConfigurationError("Route snapshot maximum age must be positive.")
        if not isinstance(self.retry_policy, RetryPolicy):
            raise FastAPIEffectsConfigurationError("Route retry policy is invalid.")
        try:
            metadata = json.loads(
                canonical_json_bytes(self.destination_metadata, maximum_bytes=16 * 1024)
            )
        except (TypeError, ValueError) as exc:
            raise FastAPIEffectsConfigurationError(
                "Destination metadata must be bounded JSON."
            ) from exc
        if not isinstance(metadata, dict):
            raise FastAPIEffectsConfigurationError("Destination metadata must be a JSON object.")
        object.__setattr__(self, "destination_metadata", _freeze_mapping(metadata))

    def to_snapshot(self) -> dict[str, object]:
        """Return the complete JSON-safe immutable execution specification."""
        return {
            "snapshot_version": 1,
            "event_type": self.event_type,
            "route_key": self.route_key,
            "route_version": self.version,
            "destination": {
                "kind": self.destination_kind,
                "key": self.destination_key,
                **_thaw_mapping(self.destination_metadata),
            },
            "authority": {
                "mode": self.authorization.value,
                "required_scopes": list(self.required_scopes),
                "service_policy": self.service_policy,
                "service_capabilities": (
                    None if self.service_capabilities is None else list(self.service_capabilities)
                ),
                "maximum_snapshot_age_seconds": self.maximum_snapshot_age_seconds,
            },
            "retry": self.retry_policy.to_dict(),
        }

    def snapshot_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_snapshot(), maximum_bytes=32 * 1024)


class RouteRegistry:
    """Register exact routes and handlers, then freeze before startup."""

    def __init__(self) -> None:
        self._routes: dict[RouteIdentity, RouteSpecification] = {}
        self._handlers: dict[RouteIdentity, Handler] = {}
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def register_handler(self, *, key: str, version: int, handler: Handler) -> None:
        self._require_mutable()
        _validate_key("Handler key", key)
        if not _is_async_callable(handler):
            raise FastAPIEffectsConfigurationError("Handlers must be asynchronous callables.")
        if not _is_positive_integer(version):
            raise FastAPIEffectsConfigurationError("Handler version must be a positive integer.")
        identity = (key, version)
        existing = self._handlers.get(identity)
        if existing is not None and existing is not handler:
            raise FastAPIEffectsConfigurationError(
                f"Duplicate handler registration: {key}@{version}."
            )
        self._handlers[identity] = handler

    def register_route(self, spec: RouteSpecification, handler: Handler) -> None:
        self._require_mutable()
        identity = (spec.route_key, spec.version)
        if identity in self._routes:
            raise FastAPIEffectsConfigurationError(
                f"Duplicate route registration: {spec.route_key}@{spec.version}."
            )
        prior_specs = [
            prior for (key, _version), prior in self._routes.items() if key == spec.route_key
        ]
        if any(prior.event_type != spec.event_type for prior in prior_specs):
            raise FastAPIEffectsConfigurationError(
                f"Route key {spec.route_key!r} cannot change its event type."
            )
        prior_versions = [prior.version for prior in prior_specs]
        if prior_versions and spec.version < max(prior_versions):
            raise FastAPIEffectsConfigurationError(
                f"Route version downgrade is not allowed for {spec.route_key!r}."
            )
        self.register_handler(key=spec.destination_key, version=spec.version, handler=handler)
        self._routes[identity] = spec

    def snapshot_service_capabilities(
        self,
        snapshots: Mapping[RouteIdentity, Iterable[str]],
    ) -> None:
        """Atomically pin validated service capabilities into route definitions."""
        self._require_mutable()
        staged: dict[RouteIdentity, RouteSpecification] = {}
        for identity, capabilities in snapshots.items():
            spec = self._routes.get(identity)
            if spec is None or spec.authorization is not AuthorizationMode.SERVICE_POLICY:
                raise FastAPIEffectsConfigurationError(
                    "Service capabilities target an unknown service-policy route."
                )
            normalized = _normalize_scopes(capabilities)
            if not set(spec.required_scopes).issubset(normalized):
                raise FastAPIEffectsConfigurationError(
                    "Named service policy lacks a required route capability."
                )
            staged[identity] = replace(spec, service_capabilities=normalized)
        self._routes.update(staged)

    def freeze(self) -> None:
        if self._frozen:
            return
        for spec in self._routes.values():
            handler_identity = (spec.destination_key, spec.version)
            if handler_identity not in self._handlers:
                raise FastAPIEffectsConfigurationError(
                    f"Route {spec.route_key}@{spec.version} has no registered handler."
                )
            if (
                spec.authorization is AuthorizationMode.SERVICE_POLICY
                and spec.service_capabilities is None
            ):
                raise FastAPIEffectsConfigurationError(
                    "Service-policy route has no resolved capability snapshot."
                )
        self._frozen = True

    def matching(self, event_type: str) -> tuple[RouteSpecification, ...]:
        _validate_event_type(event_type)
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

    def resolve_handler(self, *, key: str, version: int) -> Handler:
        """Resolve only the frozen immutable handler identity."""
        if not self._frozen:
            raise FastAPIEffectsConfigurationError(
                "Route registry must be frozen before execution."
            )
        handler = self._handlers.get((key, version))
        if handler is None:
            raise FastAPIEffectsConfigurationError(
                "Delivery references an unknown handler identity."
            )
        return handler

    def _require_mutable(self) -> None:
        if self._frozen:
            raise FastAPIEffectsConfigurationError(
                "Route registry is frozen; registration is closed."
            )


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
        handler: Callable[[EffectContext[PayloadT]], Awaitable[None]],
        *,
        required_scopes: Iterable[str] = (),
        authorization: AuthorizationMode | str = AuthorizationMode.REVALIDATE,
        service_policy: str | None = None,
        maximum_snapshot_age_seconds: int | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> Callable[[EffectContext[PayloadT]], Awaitable[None]]:
        mode = AuthorizationMode.parse(authorization)
        scopes = _normalize_scopes(required_scopes)
        if mode is AuthorizationMode.SNAPSHOT:
            if not _is_positive_integer(maximum_snapshot_age_seconds):
                raise FastAPIEffectsConfigurationError(
                    "Snapshot authorization requires a positive maximum snapshot age."
                )
            if service_policy is not None:
                raise FastAPIEffectsConfigurationError(
                    "Snapshot authorization cannot name a service policy."
                )
        elif mode is AuthorizationMode.REVALIDATE:
            if maximum_snapshot_age_seconds is not None or service_policy is not None:
                raise FastAPIEffectsConfigurationError(
                    "Revalidate authorization does not accept snapshot age or service policy."
                )
        else:
            if service_policy is None:
                raise FastAPIEffectsConfigurationError(
                    "Service-policy authorization requires a named service policy."
                )
            _validate_key("Service policy", service_policy)
            if maximum_snapshot_age_seconds is not None:
                raise FastAPIEffectsConfigurationError(
                    "Service-policy authorization does not accept snapshot maximum age."
                )

        policy = retry_policy or RetryPolicy(name="default-handler")
        if not isinstance(policy, RetryPolicy):
            raise FastAPIEffectsConfigurationError("retry_policy must be a RetryPolicy instance.")
        spec = RouteSpecification(
            event_type=self._event_type,
            route_key=self._route_key,
            version=self._version,
            destination_kind="handler",
            destination_key=self._route_key,
            required_scopes=scopes,
            authorization=mode,
            service_policy=service_policy,
            service_capabilities=None,
            maximum_snapshot_age_seconds=maximum_snapshot_age_seconds,
            retry_policy=policy,
        )
        self._registry.register_route(spec, cast(Handler, handler))
        return handler


def validate_route_declaration(*, event_type: str, route_key: str, version: int) -> None:
    _validate_event_type(event_type)
    _validate_key("Route key", route_key)
    if not _is_positive_integer(version):
        raise FastAPIEffectsConfigurationError("Route version must be a positive integer.")


def _validate_event_type(event_type: str) -> None:
    from fastapi_effects.core.event import Event

    Event(type=event_type, version=1, data=None)


def _validate_key(name: str, value: object) -> None:
    if not isinstance(value, str) or not _ROUTE_KEY.fullmatch(value):
        raise FastAPIEffectsConfigurationError(
            f"{name} must use lower-case letters, digits, dots, underscores, or hyphens."
        )


def _normalize_scopes(scopes: Iterable[str]) -> tuple[str, ...]:
    if isinstance(scopes, str):
        raise FastAPIEffectsConfigurationError("Route scopes must be a collection of strings.")
    try:
        unique_scopes = set(scopes)
    except TypeError as exc:
        raise FastAPIEffectsConfigurationError(
            "Route scopes must be an iterable of hashable strings."
        ) from exc
    if len(unique_scopes) > 256 or any(
        not isinstance(scope, str) or not _SCOPE.fullmatch(scope) for scope in unique_scopes
    ):
        raise FastAPIEffectsConfigurationError("Route contains invalid required scopes.")
    return tuple(sorted(unique_scopes))


def _is_async_callable(value: object) -> bool:
    if inspect.iscoroutinefunction(value):
        return True
    return callable(value) and inspect.iscoroutinefunction(type(value).__call__)


def _is_positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _freeze_mapping(value: dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _thaw_json(item) for key, item in value.items()}


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _thaw_mapping(value)
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value

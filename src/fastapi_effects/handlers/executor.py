"""Execute frozen handler identities with non-expanding authority."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any

from fastapi_effects.api import EffectContext
from fastapi_effects.core.context import principal_context
from fastapi_effects.core.event import Event
from fastapi_effects.core.policy import AuthorizationMode
from fastapi_effects.core.principal import Principal
from fastapi_effects.core.protocols import AuthorizationResolver, Clock, HandlerSessionProvider
from fastapi_effects.core.retry import RetryPolicy
from fastapi_effects.core.routing import RouteRegistry
from fastapi_effects.errors import (
    AuthorizationDenied,
    AuthorizationExpired,
    FastAPIEffectsConfigurationError,
)
from fastapi_effects.postgres.leasing import ClaimedDelivery
from fastapi_effects.sqlalchemy.canonical import strict_json_loads

_PAYLOAD_PREFIX = b"fastapi_effects:canonical-json:v1\n"


class HandlerExecutor:
    def __init__(
        self,
        *,
        registry: RouteRegistry,
        clock: Clock,
        application_sessions: HandlerSessionProvider,
        authorization_resolver: AuthorizationResolver | None = None,
    ) -> None:
        if not registry.frozen:
            raise FastAPIEffectsConfigurationError(
                "Handler registry must be frozen before execution."
            )
        self._registry = registry
        self._clock = clock
        self._application_sessions = application_sessions
        self._authorization_resolver = authorization_resolver

    async def execute(self, claim: ClaimedDelivery) -> None:
        snapshot = claim.route_snapshot
        destination = snapshot.get("destination")
        authority = snapshot.get("authority")
        retry_value = snapshot.get("retry")
        if not isinstance(destination, dict) or not isinstance(authority, dict):
            raise FastAPIEffectsConfigurationError("Handler delivery snapshot is invalid.")
        if not isinstance(retry_value, dict):
            raise FastAPIEffectsConfigurationError("Handler retry snapshot is invalid.")
        handler = self._registry.resolve_handler(
            key=_text(destination.get("key")),
            version=claim.delivery.route_version,
        )
        origin = Principal.from_envelope(claim.event.principal)
        effective = await self._effective_principal(origin, authority)
        body = claim.event.payload_canonical
        if not body.startswith(_PAYLOAD_PREFIX):
            raise FastAPIEffectsConfigurationError(
                "Event canonical payload revision is unsupported."
            )
        payload = strict_json_loads(body[len(_PAYLOAD_PREFIX) :])
        event = Event(
            type=claim.event.event_type,
            version=claim.event.event_version,
            data=payload,
            occurred_at=claim.event.occurred_at,
            correlation_id=claim.event.correlation_id,
            causation_id=claim.event.causation_id,
            traceparent=claim.event.traceparent,
            tracestate=claim.event.tracestate,
        )
        context = EffectContext(
            event=event,
            principal=effective,
            delivery_id=claim.delivery.delivery_id,
            route_key=claim.delivery.route_key,
            route_version=claim.delivery.route_version,
            attempt_number=claim.attempt.attempt_number,
            _application_session_provider=self._application_sessions,
        )
        policy = RetryPolicy.from_dict(retry_value)
        with principal_context(effective):
            async with asyncio.timeout(policy.handler_timeout_seconds):
                await handler(context)

    async def _effective_principal(
        self,
        origin: Principal,
        snapshot: dict[str, Any],
    ) -> Principal:
        try:
            mode = AuthorizationMode.parse(snapshot["mode"])
            required = frozenset(_string_list(snapshot["required_scopes"]))
        except (KeyError, TypeError) as exc:
            raise FastAPIEffectsConfigurationError("Authority snapshot is invalid.") from exc
        if mode is AuthorizationMode.SNAPSHOT:
            maximum_age = snapshot.get("maximum_snapshot_age_seconds")
            if not isinstance(maximum_age, int) or isinstance(maximum_age, bool):
                raise FastAPIEffectsConfigurationError("Snapshot authority age is invalid.")
            if self._clock.now() - origin.issued_at > timedelta(seconds=maximum_age):
                raise AuthorizationExpired("Snapshotted authority exceeded its maximum age.")
            effective_scopes = origin.scopes & required
        elif mode is AuthorizationMode.REVALIDATE:
            if self._authorization_resolver is None:
                raise FastAPIEffectsConfigurationError(
                    "Revalidation requires an authorization resolver."
                )
            current = await self._authorization_resolver.resolve(
                origin,
                required,
                mode,
                None,
            )
            effective_scopes = frozenset(current) & origin.scopes & required
        else:
            capabilities = snapshot.get("service_capabilities")
            policy = snapshot.get("service_policy")
            if not isinstance(policy, str) or capabilities is None:
                raise FastAPIEffectsConfigurationError("Service authority snapshot is invalid.")
            effective_scopes = frozenset(_string_list(capabilities)) & required
            if not required.issubset(effective_scopes):
                raise AuthorizationDenied("Service policy lacks required authority.")
            return Principal(
                tenant_id=origin.tenant_id,
                subject_id=f"service:{policy}",
                actor_id=origin.subject_id,
                client_id=origin.client_id,
                scopes=effective_scopes,
                issued_at=self._clock.now(),
            )
        if not required.issubset(effective_scopes):
            raise AuthorizationDenied("Effective principal lacks required authority.")
        return replace(origin, scopes=effective_scopes, credential_ref=None)


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise FastAPIEffectsConfigurationError("Handler destination is invalid.")
    return value


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise FastAPIEffectsConfigurationError("Authority scope snapshot is invalid.")
    return tuple(value)


__all__ = ["HandlerExecutor"]

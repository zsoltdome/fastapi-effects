from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_effects import (
    AuthorizationMode,
    EffectContext,
    Event,
    FastAPIEffects,
    FastAPIEffectsConfigurationError,
    FastAPIEffectsUnitOfWork,
    Principal,
    RetryPolicy,
)

TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")


class StaticPrincipalProvider:
    async def __call__(self, request: Request) -> Principal:
        del request
        return Principal(
            tenant_id=TENANT_ID,
            subject_id="user:1",
            scopes=frozenset({"invoices:read", "invoices:write"}),
        )


class StaticAuthorizationResolver:
    async def resolve(
        self,
        principal: Principal,
        required_scopes: frozenset[str],
        mode: AuthorizationMode,
        service_policy: str | None,
    ) -> frozenset[str]:
        del mode, service_policy
        return principal.scopes & required_scopes


class StaticServicePolicyRegistry:
    def __init__(self, policies: dict[str, frozenset[str]]) -> None:
        self._policies = policies

    def capabilities_for(self, service_policy: str) -> frozenset[str] | None:
        return self._policies.get(service_policy)


class StubStore:
    @property
    def name(self) -> str:
        return "milestone-one-stub"


async def handler(context: EffectContext[dict[str, str]]) -> None:
    assert context.event.type == "invoice.created"


def build_fastapi_effects(
    *,
    with_authorization_resolver: bool = True,
    service_policy_registry: StaticServicePolicyRegistry | None = None,
) -> FastAPIEffects:
    return FastAPIEffects(
        principal_provider=StaticPrincipalProvider(),
        store=StubStore(),
        authorization_resolver=(
            StaticAuthorizationResolver() if with_authorization_resolver else None
        ),
        service_policy_registry=service_policy_registry,
    )


def test_route_registration_and_exact_lookup() -> None:
    fastapi_effects = build_fastapi_effects()
    retry = RetryPolicy(name="invoice-handler")
    fastapi_effects.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=1,
    ).to_handler(
        handler,
        required_scopes={"invoices:read"},
        authorization=AuthorizationMode.REVALIDATE,
        retry_policy=retry,
    )
    assert fastapi_effects.store_name == "milestone-one-stub"
    assert [route.route_key for route in fastapi_effects.matching_routes("invoice.created")] == [
        "invoice.render_pdf"
    ]
    assert fastapi_effects.matching_routes("invoice.updated") == ()
    fastapi_effects.freeze()
    assert fastapi_effects.frozen
    fastapi_effects.freeze()
    with pytest.raises(FastAPIEffectsConfigurationError, match="frozen"):
        fastapi_effects.route(
            event_type="invoice.created",
            route_key="invoice.send_email",
        ).to_handler(handler)


def test_duplicate_route_and_version_downgrade_fail() -> None:
    fastapi_effects = build_fastapi_effects()
    fastapi_effects.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=2,
    ).to_handler(handler)
    with pytest.raises(FastAPIEffectsConfigurationError, match="Duplicate"):
        fastapi_effects.route(
            event_type="invoice.created",
            route_key="invoice.render_pdf",
            version=2,
        ).to_handler(handler)
    with pytest.raises(FastAPIEffectsConfigurationError, match="downgrade"):
        fastapi_effects.route(
            event_type="invoice.created",
            route_key="invoice.render_pdf",
            version=1,
        ).to_handler(handler)


def test_only_latest_route_version_is_active_for_new_emission() -> None:
    fastapi_effects = build_fastapi_effects()

    async def version_one(context: EffectContext[dict[str, str]]) -> None:
        del context

    async def version_two(context: EffectContext[dict[str, str]]) -> None:
        del context

    fastapi_effects.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=1,
    ).to_handler(version_one)
    fastapi_effects.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=2,
    ).to_handler(version_two)

    matches = fastapi_effects.matching_routes("invoice.created")
    assert [(route.route_key, route.version) for route in matches] == [("invoice.render_pdf", 2)]
    assert [(route.route_key, route.version) for route in fastapi_effects.routes] == [
        ("invoice.render_pdf", 1),
        ("invoice.render_pdf", 2),
    ]


def test_route_key_cannot_change_event_type() -> None:
    fastapi_effects = build_fastapi_effects()
    fastapi_effects.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=1,
    ).to_handler(handler)
    with pytest.raises(FastAPIEffectsConfigurationError, match="cannot change its event type"):
        fastapi_effects.route(
            event_type="invoice.updated",
            route_key="invoice.render_pdf",
            version=2,
        ).to_handler(handler)


def test_mode_specific_route_validation() -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="maximum snapshot age"):
        build_fastapi_effects().route(
            event_type="invoice.created",
            route_key="invoice.snapshot",
        ).to_handler(handler, authorization="snapshot")

    with pytest.raises(FastAPIEffectsConfigurationError, match="named service policy"):
        build_fastapi_effects().route(
            event_type="invoice.created",
            route_key="invoice.service",
        ).to_handler(handler, authorization="service_policy")

    def synchronous_handler(context: EffectContext[dict[str, str]]) -> None:
        del context

    with pytest.raises(FastAPIEffectsConfigurationError, match="asynchronous"):
        build_fastapi_effects().route(
            event_type="invoice.created",
            route_key="invoice.sync",
        ).to_handler(cast(Any, synchronous_handler))


def test_freeze_validates_authorization_dependencies() -> None:
    revalidate = build_fastapi_effects(with_authorization_resolver=False)
    revalidate.route(
        event_type="invoice.created",
        route_key="invoice.revalidate",
    ).to_handler(handler, authorization=AuthorizationMode.REVALIDATE)
    with pytest.raises(FastAPIEffectsConfigurationError, match="authorization resolver"):
        revalidate.freeze()
    assert not revalidate.frozen

    snapshot = build_fastapi_effects(with_authorization_resolver=False)
    snapshot.route(
        event_type="invoice.created",
        route_key="invoice.snapshot",
    ).to_handler(
        handler,
        authorization=AuthorizationMode.SNAPSHOT,
        maximum_snapshot_age_seconds=300,
    )
    snapshot.freeze()
    assert snapshot.frozen


def test_service_policy_is_resolved_and_snapshotted_at_freeze() -> None:
    fastapi_effects = build_fastapi_effects(
        service_policy_registry=StaticServicePolicyRegistry(
            {"invoice-renderer": frozenset({"invoices:read", "invoices:render"})}
        )
    )
    fastapi_effects.route(
        event_type="invoice.created",
        route_key="invoice.service",
    ).to_handler(
        handler,
        authorization=AuthorizationMode.SERVICE_POLICY,
        service_policy="invoice-renderer",
        required_scopes={"invoices:read"},
    )
    assert fastapi_effects.routes[0].service_capabilities is None
    fastapi_effects.freeze()
    assert fastapi_effects.routes[0].service_capabilities == (
        "invoices:read",
        "invoices:render",
    )


@pytest.mark.parametrize(
    ("registry", "message"),
    [
        (None, "service policy registry"),
        (StaticServicePolicyRegistry({}), "not registered"),
        (
            StaticServicePolicyRegistry({"invoice-renderer": frozenset({"invoices:render"})}),
            "lacks a required route capability",
        ),
    ],
)
def test_service_policy_freeze_fails_closed(
    registry: StaticServicePolicyRegistry | None,
    message: str,
) -> None:
    fastapi_effects = build_fastapi_effects(service_policy_registry=registry)
    fastapi_effects.route(
        event_type="invoice.created",
        route_key="invoice.service",
    ).to_handler(
        handler,
        authorization=AuthorizationMode.SERVICE_POLICY,
        service_policy="invoice-renderer",
        required_scopes={"invoices:read"},
    )
    with pytest.raises(FastAPIEffectsConfigurationError, match=message):
        fastapi_effects.freeze()
    assert not fastapi_effects.frozen
    assert fastapi_effects.routes[0].service_capabilities is None


def test_service_policy_snapshot_update_is_atomic() -> None:
    registry = StaticServicePolicyRegistry(
        {
            "allowed-policy": frozenset({"invoices:read"}),
            "insufficient-policy": frozenset({"invoices:render"}),
        }
    )
    fastapi_effects = build_fastapi_effects(service_policy_registry=registry)
    for route_key, policy in (
        ("invoice.allowed", "allowed-policy"),
        ("invoice.insufficient", "insufficient-policy"),
    ):
        fastapi_effects.route(event_type="invoice.created", route_key=route_key).to_handler(
            handler,
            authorization=AuthorizationMode.SERVICE_POLICY,
            service_policy=policy,
            required_scopes={"invoices:read"},
        )
    with pytest.raises(FastAPIEffectsConfigurationError, match="lacks a required route capability"):
        fastapi_effects.freeze()
    assert all(route.service_capabilities is None for route in fastapi_effects.routes)


def test_value_objects_validate_shape() -> None:
    now = datetime.now(UTC)
    principal = Principal(
        tenant_id=TENANT_ID,
        subject_id="user:1",
        scopes=frozenset({"invoices:read"}),
        issued_at=now,
        authentication_time=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    assert principal.scopes == frozenset({"invoices:read"})
    event = Event(type="invoice.created", version=1, data={"invoice_id": "1"})
    assert event.version == 1
    assert RetryPolicy(name="default").jitter == "full"

    with pytest.raises(FastAPIEffectsConfigurationError, match="Event type"):
        Event(type=cast(Any, 7), version=1, data={})
    with pytest.raises(FastAPIEffectsConfigurationError, match="positive integer"):
        Event(type="invoice.created", version=cast(Any, True), data={})
    with pytest.raises(FastAPIEffectsConfigurationError, match="traceparent"):
        Event(type="invoice.created", version=1, data={}, traceparent="bad\ntrace")
    with pytest.raises(FastAPIEffectsConfigurationError, match="tenant_id"):
        Principal(tenant_id=cast(Any, str(TENANT_ID)), subject_id="user:1")
    with pytest.raises(FastAPIEffectsConfigurationError, match="collection"):
        Principal(
            tenant_id=TENANT_ID,
            subject_id="user:1",
            scopes=cast(Any, "invoices:read"),
        )
    with pytest.raises(FastAPIEffectsConfigurationError, match="Lease duration"):
        RetryPolicy(
            name="bad",
            handler_timeout_seconds=60,
            lease_duration_seconds=60,
        )
    with pytest.raises(FastAPIEffectsConfigurationError, match="finite"):
        RetryPolicy(name="bad", base_delay_seconds=float("nan"))
    with pytest.raises(FastAPIEffectsConfigurationError, match="Unsupported authorization mode"):
        AuthorizationMode.parse(cast(Any, object()))


@pytest.mark.asyncio
async def test_uow_validates_before_active_transaction_operation() -> None:
    session = AsyncSession()
    uow = FastAPIEffectsUnitOfWork(
        session=session,
        principal=Principal(tenant_id=TENANT_ID, subject_id="user:1"),
    )
    event = Event(type="invoice.created", version=1, data={})
    with pytest.raises(FastAPIEffectsConfigurationError, match="provided together"):
        await uow.emit(event, dedupe_namespace="invoice-create")
    with pytest.raises(FastAPIEffectsConfigurationError, match="Dedupe key"):
        await uow.emit(
            event,
            dedupe_namespace="invoice-create",
            dedupe_key="unsafe\nkey",
        )
    with pytest.raises(FastAPIEffectsConfigurationError, match="active FastAPIEffects"):
        await uow.emit(
            event,
            dedupe_namespace="invoice-create",
            dedupe_key="request-1",
        )
    await session.close()


@pytest.mark.asyncio
async def test_fastapi_uow_dependency_resolves_principal_without_sql() -> None:
    async def session_dependency() -> AsyncSession:
        raise AssertionError("FastAPI supplies this dependency; direct test passes a session")

    fastapi_effects = build_fastapi_effects()
    resolve_principal = fastapi_effects.principal_dependency()
    dependency = fastapi_effects.uow_dependency(session_dependency)
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    session = AsyncSession()
    principal = await resolve_principal(request)
    uow = await dependency(principal=principal, session=session)
    assert uow.session is session
    assert uow.principal.tenant_id == TENANT_ID
    await session.close()


@pytest.mark.asyncio
async def test_fastapi_resolves_principal_before_session_dependency() -> None:
    events: list[str] = []

    class RejectingProvider:
        async def __call__(self, request: Request) -> Principal:
            del request
            events.append("principal")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    async def session_dependency() -> Any:
        events.append("session")
        yield cast(AsyncSession, object())

    fastapi_effects = FastAPIEffects(principal_provider=RejectingProvider())
    get_uow = fastapi_effects.uow_dependency(session_dependency)
    app = FastAPI()

    @app.get("/probe")
    async def probe(
        uow: FastAPIEffectsUnitOfWork = Depends(get_uow),
    ) -> dict[str, str]:
        del uow
        events.append("handler")
        return {"status": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/probe")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert events == ["principal"]


@pytest.mark.asyncio
async def test_effect_context_uses_only_app_session_provider() -> None:
    session = cast(AsyncSession, object())

    @asynccontextmanager
    async def provider(principal: Principal):
        assert principal.tenant_id == TENANT_ID
        yield session

    context = EffectContext(
        event=Event(type="invoice.created", version=1, data={}),
        principal=Principal(tenant_id=TENANT_ID, subject_id="user:1"),
        delivery_id=uuid4(),
        route_key="invoice.render_pdf",
        route_version=1,
        attempt_number=1,
        _application_session_provider=provider,
    )
    async with context.application_session() as provided:
        assert provided is session


def test_documented_submodule_imports_are_available() -> None:
    from fastapi_effects.postgres import PostgresStore
    from fastapi_effects.sqlalchemy import FastAPIEffectsUnitOfWork as SqlAlchemyUnitOfWork

    assert SqlAlchemyUnitOfWork is FastAPIEffectsUnitOfWork
    assert PostgresStore().name == "postgresql"


def test_postgres_store_uses_authoritative_schema() -> None:
    from fastapi_effects.postgres import PostgresStore

    with pytest.raises(FastAPIEffectsConfigurationError, match="schema name"):
        PostgresStore(schema="unsafe-schema")
    assert PostgresStore().schema == "fastapi_effects"
    assert not hasattr(PostgresStore(), "require_implementation")

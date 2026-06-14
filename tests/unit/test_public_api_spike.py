from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen import (
    AuthorizationMode,
    EffectContext,
    Event,
    Mergen,
    MergenConfigurationError,
    MergenUnitOfWork,
    MilestoneNotImplementedError,
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
    def capabilities_for(self, service_policy: str) -> frozenset[str] | None:
        if service_policy == "invoice-system":
            return frozenset({"invoices:read", "invoices:write"})
        return None


class StubStore:
    @property
    def name(self) -> str:
        return "milestone-one-stub"


async def handler(context: EffectContext[dict[str, str]]) -> None:
    assert context.event.type == "invoice.created"


def build_mergen() -> Mergen:
    return Mergen(
        principal_provider=StaticPrincipalProvider(),
        store=StubStore(),
        authorization_resolver=StaticAuthorizationResolver(),
        service_policy_registry=StaticServicePolicyRegistry(),
    )


def test_route_registration_and_exact_lookup() -> None:
    mergen = build_mergen()
    retry = RetryPolicy(name="invoice-handler")
    mergen.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=1,
    ).to_handler(
        handler,
        required_scopes={"invoices:read"},
        authorization=AuthorizationMode.REVALIDATE,
        retry_policy=retry,
    )
    assert mergen.store_name == "milestone-one-stub"
    assert [route.route_key for route in mergen.matching_routes("invoice.created")] == [
        "invoice.render_pdf"
    ]
    assert mergen.matching_routes("invoice.updated") == ()
    mergen.freeze()
    assert mergen.frozen
    mergen.freeze()  # idempotent startup calls are safe
    with pytest.raises(MergenConfigurationError, match="frozen"):
        mergen.route(
            event_type="invoice.created",
            route_key="invoice.send_email",
        ).to_handler(handler)


def test_duplicate_route_and_version_downgrade_fail() -> None:
    mergen = build_mergen()
    mergen.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=2,
    ).to_handler(handler)
    with pytest.raises(MergenConfigurationError, match="Duplicate"):
        mergen.route(
            event_type="invoice.created",
            route_key="invoice.render_pdf",
            version=2,
        ).to_handler(handler)
    with pytest.raises(MergenConfigurationError, match="downgrade"):
        mergen.route(
            event_type="invoice.created",
            route_key="invoice.render_pdf",
            version=1,
        ).to_handler(handler)



def test_only_latest_route_version_is_active_for_new_emission() -> None:
    mergen = build_mergen()

    async def version_one(context: EffectContext[dict[str, str]]) -> None:
        del context

    async def version_two(context: EffectContext[dict[str, str]]) -> None:
        del context

    mergen.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=1,
    ).to_handler(version_one)
    mergen.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=2,
    ).to_handler(version_two)

    matches = mergen.matching_routes("invoice.created")
    assert [(route.route_key, route.version) for route in matches] == [
        ("invoice.render_pdf", 2)
    ]
    assert [(route.route_key, route.version) for route in mergen.routes] == [
        ("invoice.render_pdf", 1),
        ("invoice.render_pdf", 2),
    ]


def test_route_key_cannot_change_event_type() -> None:
    mergen = build_mergen()
    mergen.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
        version=1,
    ).to_handler(handler)
    with pytest.raises(MergenConfigurationError, match="cannot change its event type"):
        mergen.route(
            event_type="invoice.updated",
            route_key="invoice.render_pdf",
            version=2,
        ).to_handler(handler)

def test_mode_specific_route_validation() -> None:
    with pytest.raises(MergenConfigurationError, match="maximum snapshot age"):
        build_mergen().route(
            event_type="invoice.created",
            route_key="invoice.snapshot",
        ).to_handler(handler, authorization="snapshot")

    with pytest.raises(MergenConfigurationError, match="named service policy"):
        build_mergen().route(
            event_type="invoice.created",
            route_key="invoice.service",
        ).to_handler(handler, authorization="service_policy")


def test_route_rejects_sync_handlers_and_string_scopes() -> None:
    def sync_handler(context: EffectContext[dict[str, str]]) -> None:
        del context

    with pytest.raises(MergenConfigurationError, match="asynchronous"):
        build_mergen().route(
            event_type="invoice.created",
            route_key="invoice.sync",
        ).to_handler(cast(Any, sync_handler))
    with pytest.raises(MergenConfigurationError, match="collection of strings"):
        build_mergen().route(
            event_type="invoice.created",
            route_key="invoice.bad_scopes",
        ).to_handler(handler, required_scopes=cast(Any, "invoices:read"))


def test_freeze_requires_authorization_resolver() -> None:
    mergen = Mergen(principal_provider=StaticPrincipalProvider(), store=StubStore())
    mergen.route(
        event_type="invoice.created",
        route_key="invoice.render_pdf",
    ).to_handler(handler, authorization="revalidate")
    with pytest.raises(MergenConfigurationError, match="authorization resolver"):
        mergen.freeze()


def test_freeze_validates_named_service_policy() -> None:
    mergen = build_mergen()
    mergen.route(
        event_type="invoice.created",
        route_key="invoice.service",
    ).to_handler(
        handler,
        authorization="service_policy",
        service_policy="unknown-service",
    )
    with pytest.raises(MergenConfigurationError, match="not registered"):
        mergen.freeze()


def test_service_policy_capabilities_are_snapshotted() -> None:
    mergen = build_mergen()
    mergen.route(
        event_type="invoice.created",
        route_key="invoice.service",
    ).to_handler(
        handler,
        authorization="service_policy",
        service_policy="invoice-system",
        required_scopes={"invoices:read"},
    )
    mergen.freeze()
    route = mergen.routes[0]
    assert route.service_capabilities == ("invoices:read", "invoices:write")


def test_value_objects_validate_shape() -> None:
    now = datetime.now(timezone.utc)
    principal = Principal(
        tenant_id=TENANT_ID,
        subject_id="user:1",
        scopes=frozenset({"invoices:read", "invoices:read"}),
        issued_at=now,
        authentication_time=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    assert principal.scopes == frozenset({"invoices:read"})
    event = Event(type="invoice.created", version=1, data={"invoice_id": "1"})
    assert event.version == 1
    assert RetryPolicy(name="default").jitter == "full"

    with pytest.raises(MergenConfigurationError, match="Event type"):
        Event(type="Invoice Created", version=1, data={})
    with pytest.raises(MergenConfigurationError, match="Lease duration"):
        RetryPolicy(
            name="bad",
            handler_timeout_seconds=60,
            lease_duration_seconds=60,
        )
    with pytest.raises(MergenConfigurationError, match="positive integer"):
        Event(type="invoice.created", version=cast(Any, True), data={})
    with pytest.raises(MergenConfigurationError, match="tenant_id"):
        Principal(tenant_id=cast(Any, "tenant"), subject_id="user:1")
    with pytest.raises(MergenConfigurationError, match="iterable of strings"):
        Principal(
            tenant_id=TENANT_ID,
            subject_id="user:1",
            scopes=cast(Any, "invoices:read"),
        )
    with pytest.raises(MergenConfigurationError, match="finite numbers"):
        RetryPolicy(name="bad", base_delay_seconds=float("inf"))
    with pytest.raises(MergenConfigurationError, match="Unsupported authorization"):
        AuthorizationMode.parse(cast(Any, []))


@pytest.mark.asyncio
async def test_uow_spike_fails_before_session_operation() -> None:
    session = cast(AsyncSession, object())
    uow = MergenUnitOfWork(
        session=session,
        principal=Principal(tenant_id=TENANT_ID, subject_id="user:1"),
    )
    with pytest.raises(MilestoneNotImplementedError, match="Milestone 2"):
        async with uow:
            raise AssertionError("unreachable")
    with pytest.raises(MilestoneNotImplementedError, match="Milestone 2"):
        await uow.emit(Event(type="invoice.created", version=1, data={}))


@pytest.mark.asyncio
async def test_fastapi_uow_dependency_resolves_principal_without_sql() -> None:
    async def session_dependency() -> AsyncSession:
        raise AssertionError("FastAPI supplies this dependency; direct test passes a session")

    mergen = build_mergen()
    dependency = mergen.uow_dependency(session_dependency)
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    session = cast(AsyncSession, object())
    uow = await dependency(request=request, session=session)
    assert uow.session is session
    assert uow.principal.tenant_id == TENANT_ID


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

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen import AuthorizationMode, EffectContext, Mergen, Principal, RetryPolicy
from fastapi_mergen.core.context import current_principal
from fastapi_mergen.core.delivery import (
    AttemptOutcome,
    AttemptRecord,
    DeliveryRecord,
    DeliveryState,
)
from fastapi_mergen.core.event import EventRecord
from fastapi_mergen.errors import AuthorizationExpired
from fastapi_mergen.postgres.leasing import ClaimedDelivery
from fastapi_mergen.sqlalchemy.canonical import canonical_sha256, versioned_canonical_bytes

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class Resolver:
    async def resolve(
        self,
        principal: Principal,
        required_scopes: frozenset[str],
        mode: AuthorizationMode,
        service_policy: str | None,
    ) -> frozenset[str]:
        del principal, required_scopes, mode, service_policy
        return frozenset({"invoice:read", "admin"})


async def principal_provider(request: object) -> Principal:
    del request
    raise AssertionError


def _claim(mergen: Mergen, principal: Principal) -> ClaimedDelivery:
    route = mergen.routes[0]
    delivery_id = uuid4()
    token = uuid4()
    payload = {"invoice_id": "inv-1"}
    event_id = uuid4()
    return ClaimedDelivery(
        event=EventRecord(
            event_id=event_id,
            tenant_id=principal.tenant_id,
            event_type="invoice.created",
            event_version=1,
            canonical_version=1,
            payload_canonical=versioned_canonical_bytes(payload),
            payload_sha256=canonical_sha256(payload),
            principal=principal.to_envelope(),
            occurred_at=NOW,
            created_at=NOW,
        ),
        delivery=DeliveryRecord(
            delivery_id=delivery_id,
            tenant_id=principal.tenant_id,
            event_id=event_id,
            route_key=route.route_key,
            route_version=route.version,
            destination_kind=route.destination_kind,
            destination_key=route.destination_key,
            route_snapshot=route.snapshot_bytes(),
            state=DeliveryState.LEASED,
            attempts_started=1,
            created_at=NOW,
            updated_at=NOW,
            next_attempt_at=NOW,
            lease_token=token,
            lease_expires_at=NOW + timedelta(seconds=10),
        ),
        attempt=AttemptRecord(
            attempt_id=uuid4(),
            tenant_id=principal.tenant_id,
            delivery_id=delivery_id,
            attempt_number=1,
            lease_token=token,
            outcome=AttemptOutcome.STARTED,
            started_at=NOW,
        ),
        route_snapshot=route.to_snapshot(),
    )


@pytest.mark.asyncio
async def test_revalidation_never_expands_authority_and_sessions_are_fresh() -> None:
    sessions: list[object] = []
    principals: list[Principal] = []

    @asynccontextmanager
    async def application_session(principal: Principal):
        session = object()
        sessions.append(session)
        assert principal.tenant_id == origin.tenant_id
        yield cast(AsyncSession, session)

    async def handler(context: EffectContext[dict[str, str]]) -> None:
        principals.append(context.principal)
        assert current_principal() == context.principal
        async with context.application_session() as session:
            assert session is sessions[-1]

    origin = Principal(
        tenant_id=uuid4(),
        subject_id="user:42",
        scopes=frozenset({"invoice:read", "invoice:write"}),
        issued_at=NOW,
    )
    mergen = Mergen(
        principal_provider=principal_provider,
        authorization_resolver=Resolver(),
        handler_session_provider=application_session,
        clock=FixedClock(),
    )
    mergen.route(event_type="invoice.created", route_key="invoice.render").to_handler(
        handler,
        required_scopes={"invoice:read"},
        authorization=AuthorizationMode.REVALIDATE,
        retry_policy=RetryPolicy(
            name="handler-test", handler_timeout_seconds=1, lease_duration_seconds=10
        ),
    )
    executor = mergen.handler_executor()
    await executor.execute(_claim(mergen, origin))
    await executor.execute(_claim(mergen, origin))

    assert [principal.scopes for principal in principals] == [
        frozenset({"invoice:read"}),
        frozenset({"invoice:read"}),
    ]
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert current_principal(required=False) is None


@pytest.mark.asyncio
async def test_snapshot_expiry_and_handler_failure_reset_context() -> None:
    @asynccontextmanager
    async def application_session(principal: Principal):
        del principal
        yield cast(AsyncSession, object())

    async def handler(context: EffectContext[Any]) -> None:
        del context
        raise RuntimeError("receiver-controlled details")

    expired = Principal(
        tenant_id=uuid4(),
        subject_id="user:expired",
        scopes=frozenset({"invoice:read"}),
        issued_at=NOW - timedelta(minutes=2),
    )
    mergen = Mergen(
        principal_provider=principal_provider,
        handler_session_provider=application_session,
        clock=FixedClock(),
    )
    mergen.route(event_type="invoice.created", route_key="invoice.render").to_handler(
        handler,
        required_scopes={"invoice:read"},
        authorization=AuthorizationMode.SNAPSHOT,
        maximum_snapshot_age_seconds=30,
        retry_policy=RetryPolicy(
            name="handler-test", handler_timeout_seconds=1, lease_duration_seconds=10
        ),
    )
    executor = mergen.handler_executor()
    with pytest.raises(AuthorizationExpired):
        await executor.execute(_claim(mergen, expired))
    assert current_principal(required=False) is None

    current = Principal(
        tenant_id=expired.tenant_id,
        subject_id="user:current",
        scopes=expired.scopes,
        issued_at=NOW,
    )
    with pytest.raises(RuntimeError, match="receiver-controlled"):
        await executor.execute(_claim(mergen, current))
    assert current_principal(required=False) is None

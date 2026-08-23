from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fastapi_mergen.core.delivery import (
    AttemptOutcome,
    AttemptRecord,
    DeliveryRecord,
    DeliveryState,
)
from fastapi_mergen.core.event import EventRecord
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.retry import RetryPolicy
from fastapi_mergen.errors import PermanentDeliveryError
from fastapi_mergen.postgres.leasing import ClaimedDelivery
from fastapi_mergen.sqlalchemy.canonical import canonical_sha256, versioned_canonical_bytes
from fastapi_mergen.webhooks.address_policy import EndpointTarget
from fastapi_mergen.webhooks.http11 import HttpResponseMetadata
from fastapi_mergen.webhooks.secrets import SigningSecret
from fastapi_mergen.webhooks.sink import WebhookDeliverySink
from fastapi_mergen.webhooks.transport import TransportLimits, TransportResult

pytestmark = pytest.mark.security


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        del args


class _Sessions:
    def __call__(self) -> _SessionContext:
        return _SessionContext()


class _Secrets:
    async def eligible_for_signing(self, *args: object, **kwargs: object) -> tuple[SigningSecret]:
        del args, kwargs
        return (SigningSecret(version=1, material=b"s" * 32),)


class _Resolver:
    def __init__(self) -> None:
        self.hostnames: list[str] = []

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        assert port == 443
        self.hostnames.append(hostname)
        return ("93.184.216.34" if len(self.hostnames) == 1 else "93.184.216.35",)


class _Transport:
    def __init__(self, *, maximum_redirects: int) -> None:
        self.limits = TransportLimits(maximum_redirects=maximum_redirects)
        self.requests: list[tuple[str, str, bytes, Mapping[str, str]]] = []

    async def send(
        self,
        *,
        endpoint: EndpointTarget,
        connected_ip: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> TransportResult:
        self.requests.append((endpoint.url, connected_ip, body, headers))
        if len(self.requests) == 1:
            response = HttpResponseMetadata(
                status_code=307,
                headers={"location": "https://redirect.example/next"},
                discarded_body_bytes=0,
            )
        else:
            response = HttpResponseMetadata(status_code=202, headers={}, discarded_body_bytes=0)
        return TransportResult(connected_ip=connected_ip, response=response)


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 30, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_enabled_redirect_revalidates_dns_and_preserves_signed_body() -> None:
    resolver = _Resolver()
    transport = _Transport(maximum_redirects=1)
    sink = WebhookDeliverySink(
        sessions=_Sessions(),  # type: ignore[arg-type]
        secrets=_Secrets(),  # type: ignore[arg-type]
        resolver=resolver,
        transport=transport,  # type: ignore[arg-type]
        clock=_Clock(),
    )

    result = await sink.deliver_attempt(_claim())

    assert resolver.hostnames == ["origin.example", "redirect.example"]
    assert [request[1] for request in transport.requests] == [
        "93.184.216.34",
        "93.184.216.35",
    ]
    assert transport.requests[0][2:] == transport.requests[1][2:]
    assert result.status_code == 202


@pytest.mark.asyncio
async def test_redirects_are_terminal_when_not_explicitly_enabled() -> None:
    transport = _Transport(maximum_redirects=0)
    sink = WebhookDeliverySink(
        sessions=_Sessions(),  # type: ignore[arg-type]
        secrets=_Secrets(),  # type: ignore[arg-type]
        resolver=_Resolver(),
        transport=transport,  # type: ignore[arg-type]
        clock=_Clock(),
    )

    with pytest.raises(PermanentDeliveryError) as raised:
        await sink.deliver_attempt(_claim())

    assert raised.value.code == "webhook.redirect"
    assert len(transport.requests) == 1


def _claim() -> ClaimedDelivery:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    event_id = UUID("22222222-2222-4222-8222-222222222222")
    delivery_id = UUID("33333333-3333-4333-8333-333333333333")
    attempt_id = UUID("44444444-4444-4444-8444-444444444444")
    lease_token = UUID("55555555-5555-4555-8555-555555555555")
    payload: dict[str, object] = {"invoice": "42"}
    principal = Principal(tenant_id=tenant_id, subject_id="user:redirect")
    retry = RetryPolicy(
        name="redirect-test",
        maximum_elapsed_seconds=3600,
        maximum_delay_seconds=60,
        handler_timeout_seconds=10,
        lease_duration_seconds=30,
    )
    route_snapshot = {
        "destination": {
            "endpoint_url": "https://origin.example/start",
            "secret_set_id": "66666666-6666-4666-8666-666666666666",
            "subscription_id": "77777777-7777-4777-8777-777777777777",
        },
        "retry": retry.to_dict(),
    }
    event = EventRecord(
        event_id=event_id,
        tenant_id=tenant_id,
        event_type="invoice.created",
        event_version=1,
        canonical_version=1,
        payload_canonical=versioned_canonical_bytes(payload),
        payload_sha256=canonical_sha256(payload),
        principal=principal.to_envelope(),
        occurred_at=now,
        created_at=now,
    )
    delivery = DeliveryRecord(
        delivery_id=delivery_id,
        tenant_id=tenant_id,
        event_id=event_id,
        route_key="webhook.redirect",
        route_version=1,
        destination_kind="webhook",
        destination_key="webhook.redirect",
        route_snapshot=b"{}",
        state=DeliveryState.LEASED,
        attempts_started=1,
        created_at=now,
        updated_at=now,
        next_attempt_at=now,
        lease_token=lease_token,
        lease_expires_at=now + timedelta(seconds=30),
    )
    attempt = AttemptRecord(
        attempt_id=attempt_id,
        tenant_id=tenant_id,
        delivery_id=delivery_id,
        attempt_number=1,
        lease_token=lease_token,
        outcome=AttemptOutcome.STARTED,
        started_at=now,
    )
    return ClaimedDelivery(
        event=event,
        delivery=delivery,
        attempt=attempt,
        route_snapshot=route_snapshot,
    )

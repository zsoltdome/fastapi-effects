from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from fastapi_mergen import RetryPolicy
from fastapi_mergen.errors import MergenConfigurationError, PermanentDeliveryError
from fastapi_mergen.postgres.relay import PollingRelay
from fastapi_mergen.webhooks.secrets import (
    MasterKey,
    StaticMasterKeyProvider,
    WebhookSecretService,
)
from fastapi_mergen.webhooks.sink import WebhookDeliverySink


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


class _ScalarResult:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class _Session:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    async def scalars(self, statement: object) -> _ScalarResult:
        del statement
        return _ScalarResult(self.rows)


class _SessionContext:
    def __init__(self, rows: list[object]) -> None:
        self.session = _Session(rows)

    async def __aenter__(self) -> _Session:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        del args


class _Sessions:
    def __init__(self, rows: list[object] | None = None) -> None:
        self.rows = rows or []

    def __call__(self) -> _SessionContext:
        return _SessionContext(self.rows)


def _claim(now: datetime) -> SimpleNamespace:
    delivery_id = uuid4()
    retry = RetryPolicy(
        name="webhook-key-test",
        maximum_elapsed_seconds=60,
        maximum_delay_seconds=10,
        handler_timeout_seconds=10,
        lease_duration_seconds=20,
    )
    return SimpleNamespace(
        delivery=SimpleNamespace(
            delivery_id=delivery_id,
            tenant_id=uuid4(),
            destination_kind="webhook",
            created_at=now,
            lease_expires_at=now + timedelta(seconds=20),
            replay_of=None,
        ),
        attempt=SimpleNamespace(attempt_id=uuid4(), started_at=now),
        event=SimpleNamespace(event_id=uuid4(), traceparent=None),
        route_snapshot={
            "retry": retry.to_dict(),
            "destination": {
                "endpoint_url": "https://receiver.example/hooks",
                "secret_set_id": str(uuid4()),
                "subscription_id": str(uuid4()),
            },
        },
    )


class _Leases:
    def __init__(self, claims: tuple[SimpleNamespace, ...]) -> None:
        self.claims = claims
        self.succeeded: list[UUID] = []
        self.failed: list[tuple[UUID, str]] = []

    async def reconcile_expired(self, session: object, **kwargs: object) -> int:
        del session, kwargs
        return 0

    async def claim(self, session: object, **kwargs: object) -> tuple[SimpleNamespace, ...]:
        del session, kwargs
        return self.claims

    async def succeed(self, session: object, claim: SimpleNamespace, **kwargs: object) -> None:
        del session, kwargs
        self.succeeded.append(claim.delivery.delivery_id)

    async def fail(
        self,
        session: object,
        claim: SimpleNamespace,
        error: PermanentDeliveryError,
        **kwargs: object,
    ) -> None:
        del session, kwargs
        self.failed.append((claim.delivery.delivery_id, error.code))


def _secret_service() -> WebhookSecretService:
    return WebhookSecretService(
        StaticMasterKeyProvider(
            keys=(MasterKey("configured", b"k" * 32),),
            current_key_id="configured",
        )
    )


@pytest.mark.asyncio
async def test_empty_real_secret_lookup_is_terminal_and_does_not_cancel_sibling() -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    unsignable = _claim(now)
    healthy = _claim(now)
    actual_sink = WebhookDeliverySink(
        sessions=_Sessions(),  # type: ignore[arg-type]
        secrets=_secret_service(),
        clock=_Clock(now),
    )
    healthy_executed = asyncio.Event()

    class RoutedSink:
        async def execute(self, claim: SimpleNamespace) -> None:
            if claim is unsignable:
                await actual_sink.execute(claim)  # type: ignore[arg-type]
            else:
                healthy_executed.set()

    leases = _Leases((unsignable, healthy))
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=RoutedSink(),  # type: ignore[arg-type]
        leases=leases,  # type: ignore[arg-type]
        clock=_Clock(now),
    )

    assert await relay.run_once() == 2
    assert healthy_executed.is_set()
    assert leases.succeeded == [healthy.delivery.delivery_id]
    assert leases.failed == [(unsignable.delivery.delivery_id, "webhook.no_eligible_signing_key")]


@pytest.mark.asyncio
async def test_missing_master_key_configuration_still_surfaces() -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    row = SimpleNamespace(
        secret_version=1,
        key_id="missing",
        nonce=b"n" * 12,
        ciphertext=b"ciphertext",
    )
    sink = WebhookDeliverySink(
        sessions=_Sessions([row]),  # type: ignore[arg-type]
        secrets=_secret_service(),
        clock=_Clock(now),
    )

    with pytest.raises(MergenConfigurationError, match="master key"):
        await sink.execute(_claim(now))  # type: ignore[arg-type]

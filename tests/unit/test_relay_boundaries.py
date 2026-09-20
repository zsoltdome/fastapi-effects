from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from fastapi_effects import Principal, RetryPolicy
from fastapi_effects.core.delivery import (
    AttemptOutcome,
    AttemptRecord,
    DeliveryRecord,
    DeliveryState,
)
from fastapi_effects.core.event import EventRecord
from fastapi_effects.errors import (
    FastAPIEffectsConfigurationError,
    LeaseLost,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_effects.executors.taskiq.adapter import TaskiqDeliverySink
from fastapi_effects.executors.taskiq.envelope import TaskiqHandoffEnvelope
from fastapi_effects.observability.events import RuntimeEvent, RuntimeEventKind
from fastapi_effects.postgres.leasing import ClaimedDelivery
from fastapi_effects.postgres.relay import PollingRelay, RelayConfig, SinkDisposition


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        del args


class _Sessions:
    def __call__(self) -> _SessionContext:
        return _SessionContext()


class _Events:
    def __init__(self) -> None:
        self.values: list[RuntimeEvent] = []

    def record(self, event: RuntimeEvent) -> None:
        self.values.append(event)


class _Leases:
    def __init__(self, claims: tuple[ClaimedDelivery, ...], lost: UUID | None = None) -> None:
        self.claims = claims
        self.lost = lost
        self.succeeded: list[UUID] = []
        self.failures: list[str] = []

    async def reconcile_expired(self, session: object, **kwargs: object) -> int:
        del session, kwargs
        return 0

    async def claim(self, session: object, **kwargs: object) -> tuple[ClaimedDelivery, ...]:
        del session, kwargs
        return self.claims

    async def succeed(
        self,
        session: object,
        claim: ClaimedDelivery,
        **kwargs: object,
    ) -> None:
        del session, kwargs
        if claim.delivery.delivery_id == self.lost:
            raise LeaseLost(delivery_id=claim.delivery.delivery_id)
        self.succeeded.append(claim.delivery.delivery_id)

    async def fail(
        self,
        session: object,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
        **kwargs: object,
    ) -> DeliveryState:
        del session, kwargs
        if claim.delivery.delivery_id == self.lost:
            raise LeaseLost(delivery_id=claim.delivery.delivery_id)
        self.failures.append(error.code)
        return DeliveryState.RETRY_WAIT


def _claim(now: datetime, *, handler_timeout: float = 1.0) -> ClaimedDelivery:
    tenant_id = uuid4()
    delivery_id = uuid4()
    attempt_id = uuid4()
    event_id = uuid4()
    token = uuid4()
    policy = RetryPolicy(
        name="relay-boundary",
        maximum_elapsed_seconds=60,
        maximum_delay_seconds=10,
        handler_timeout_seconds=handler_timeout,
        lease_duration_seconds=2,
    )
    event = EventRecord(
        event_id=event_id,
        tenant_id=tenant_id,
        event_type="relay.test",
        event_version=1,
        canonical_version=1,
        payload_canonical=b"payload",
        payload_sha256=b"d" * 32,
        principal=Principal(
            tenant_id=tenant_id,
            subject_id="test:relay",
            issued_at=now,
        ).to_envelope(),
        occurred_at=now,
        created_at=now,
    )
    delivery = DeliveryRecord(
        delivery_id=delivery_id,
        tenant_id=tenant_id,
        event_id=event_id,
        route_key="relay.test",
        route_version=1,
        destination_kind="handler",
        destination_key="relay.test",
        route_snapshot=b"snapshot",
        state=DeliveryState.LEASED,
        attempts_started=1,
        created_at=now,
        updated_at=now,
        next_attempt_at=now,
        lease_token=token,
        lease_expires_at=now + timedelta(seconds=2),
    )
    attempt = AttemptRecord(
        attempt_id=attempt_id,
        tenant_id=tenant_id,
        delivery_id=delivery_id,
        attempt_number=1,
        lease_token=token,
        outcome=AttemptOutcome.STARTED,
        started_at=now,
    )
    return ClaimedDelivery(
        event=event,
        delivery=delivery,
        attempt=attempt,
        route_snapshot={"retry": policy.to_dict()},
    )


@pytest.mark.asyncio
async def test_lease_loss_does_not_cancel_an_unrelated_delivery() -> None:
    now = datetime.now(UTC)
    slow = _claim(now)
    lost = _claim(now)
    completed: list[UUID] = []

    class Sink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            if claim.delivery.delivery_id == slow.delivery.delivery_id:
                await asyncio.sleep(0.02)
            completed.append(claim.delivery.delivery_id)

    leases = _Leases((slow, lost), lost=lost.delivery.delivery_id)
    events = _Events()
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=Sink(),
        leases=leases,  # type: ignore[arg-type]
        clock=_Clock(now),
        event_sink=events,
    )
    assert await relay.run_once() == 2
    assert set(completed) == {slow.delivery.delivery_id, lost.delivery.delivery_id}
    assert leases.succeeded == [slow.delivery.delivery_id]
    assert [event.kind for event in events.values] == [RuntimeEventKind.LEASE_LOST]


@pytest.mark.asyncio
async def test_failure_finalization_lease_loss_does_not_cancel_a_sibling() -> None:
    now = datetime.now(UTC)
    lost = _claim(now)
    sibling = _claim(now)
    completed: list[UUID] = []

    class Sink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            if claim.delivery.delivery_id == lost.delivery.delivery_id:
                raise RetryableDeliveryError(
                    code="controlled.retry",
                    summary="Controlled retryable failure.",
                )
            await asyncio.sleep(0.02)
            completed.append(claim.delivery.delivery_id)

    leases = _Leases((lost, sibling), lost=lost.delivery.delivery_id)
    events = _Events()
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=Sink(),
        leases=leases,  # type: ignore[arg-type]
        clock=_Clock(now),
        event_sink=events,
    )
    assert await relay.run_once() == 2
    assert completed == [sibling.delivery.delivery_id]
    assert leases.succeeded == [sibling.delivery.delivery_id]
    assert [event.kind for event in events.values] == [RuntimeEventKind.LEASE_LOST]


@pytest.mark.asyncio
async def test_poisoned_delivery_failure_does_not_cancel_an_unrelated_tenant() -> None:
    now = datetime.now(UTC)
    poisoned = _claim(now)
    healthy = _claim(now)
    completed: list[UUID] = []

    class Sink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            if claim.delivery.delivery_id == poisoned.delivery.delivery_id:
                raise PermanentDeliveryError(
                    code="webhook.endpoint_invalid",
                    summary="Controlled persisted endpoint failure.",
                )
            await asyncio.sleep(0.01)
            completed.append(claim.delivery.delivery_id)

    leases = _Leases((poisoned, healthy))
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=Sink(),
        leases=leases,  # type: ignore[arg-type]
        clock=_Clock(now),
    )

    assert await relay.run_once() == 2
    assert completed == [healthy.delivery.delivery_id]
    assert leases.succeeded == [healthy.delivery.delivery_id]
    assert leases.failures == ["webhook.endpoint_invalid"]


@pytest.mark.asyncio
async def test_relay_enforces_the_aggregate_attempt_deadline() -> None:
    now = datetime.now(UTC)
    claim = _claim(now, handler_timeout=0.01)

    class StalledSink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            del claim
            await asyncio.Event().wait()

    leases = _Leases((claim,))
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=StalledSink(),
        leases=leases,  # type: ignore[arg-type]
        clock=_Clock(now),
    )
    started = asyncio.get_running_loop().time()
    await relay.execute_claim(claim)
    assert asyncio.get_running_loop().time() - started < 0.1
    assert leases.failures == ["execution.timeout"]


@pytest.mark.asyncio
async def test_taskiq_broker_enqueue_uses_the_parent_attempt_deadline() -> None:
    now = datetime.now(UTC)
    claim = _claim(now, handler_timeout=0.01)
    envelope = TaskiqHandoffEnvelope(
        tenant_id=claim.delivery.tenant_id,
        handoff_id=uuid4(),
        delivery_id=claim.delivery.delivery_id,
        attempt_id=claim.attempt.attempt_id,
        task_id=f"fastapi_effects_{claim.attempt.attempt_id}",
        handoff_token=uuid4(),
    )

    class Store:
        async def prepare(self, *args: object, **kwargs: object) -> TaskiqHandoffEnvelope:
            del args, kwargs
            return envelope

    class Kicker:
        def with_labels(self, **labels: str) -> Kicker:
            del labels
            return self

        def with_task_id(self, task_id: str) -> Kicker:
            del task_id
            return self

        async def kiq(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    class Task:
        def kicker(self) -> Kicker:
            return Kicker()

    sink = TaskiqDeliverySink(
        sessions=_Sessions(),  # type: ignore[arg-type]
        task=Task(),
        store=Store(),  # type: ignore[arg-type]
        clock=_Clock(now),
    )
    started = asyncio.get_running_loop().time()
    assert await sink.execute(claim) is SinkDisposition.DEFERRED
    assert asyncio.get_running_loop().time() - started < 0.1


@pytest.mark.asyncio
async def test_relay_escalates_configuration_errors_without_retrying_delivery() -> None:
    now = datetime.now(UTC)
    claim = _claim(now)

    class InvalidSink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            del claim
            raise FastAPIEffectsConfigurationError("Controlled programming error.")

    leases = _Leases((claim,))
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=InvalidSink(),
        leases=leases,  # type: ignore[arg-type]
        clock=_Clock(now),
    )
    with pytest.raises(FastAPIEffectsConfigurationError, match="programming error"):
        await relay.execute_claim(claim)
    assert leases.failures == []


@pytest.mark.asyncio
async def test_relay_supervisor_resumes_polling_after_transient_database_failure() -> None:
    class FlakyLeases(_Leases):
        def __init__(self) -> None:
            super().__init__(())
            self.reconcile_calls = 0
            self.resumed = asyncio.Event()

        async def reconcile_expired(self, session: object, **kwargs: object) -> int:
            del session, kwargs
            self.reconcile_calls += 1
            if self.reconcile_calls == 1:
                raise OperationalError("controlled", {}, RuntimeError("database unavailable"))
            self.resumed.set()
            return 0

    leases = FlakyLeases()
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=object(),  # type: ignore[arg-type]
        leases=leases,  # type: ignore[arg-type]
        config=RelayConfig(poll_interval_seconds=0.001),
    )
    task = asyncio.create_task(relay.run())
    await asyncio.wait_for(leases.resumed.wait(), timeout=0.1)
    relay.request_stop()
    await asyncio.wait_for(task, timeout=0.1)
    assert leases.reconcile_calls >= 2


@pytest.mark.asyncio
async def test_relay_supervisor_resumes_after_raw_connection_refusal() -> None:
    class FlakyLeases(_Leases):
        def __init__(self) -> None:
            super().__init__(())
            self.calls = 0
            self.resumed = asyncio.Event()

        async def reconcile_expired(self, session: object, **kwargs: object) -> int:
            del session, kwargs
            self.calls += 1
            if self.calls == 1:
                raise ConnectionRefusedError("controlled database refusal")
            self.resumed.set()
            return 0

    leases = FlakyLeases()
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=object(),  # type: ignore[arg-type]
        leases=leases,  # type: ignore[arg-type]
        config=RelayConfig(poll_interval_seconds=0.001),
    )
    task = asyncio.create_task(relay.run())
    await asyncio.wait_for(leases.resumed.wait(), timeout=0.1)
    relay.request_stop()
    await asyncio.wait_for(task, timeout=0.1)
    assert leases.calls >= 2


@pytest.mark.asyncio
async def test_relay_supervisor_handles_generic_invalidated_dbapi_error() -> None:
    class FlakyLeases(_Leases):
        def __init__(self) -> None:
            super().__init__(())
            self.calls = 0
            self.resumed = asyncio.Event()

        async def reconcile_expired(self, session: object, **kwargs: object) -> int:
            del session, kwargs
            self.calls += 1
            if self.calls == 1:
                raise DBAPIError(
                    "controlled",
                    {},
                    RuntimeError("connection disappeared"),
                    connection_invalidated=True,
                )
            self.resumed.set()
            return 0

    leases = FlakyLeases()
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=object(),  # type: ignore[arg-type]
        leases=leases,  # type: ignore[arg-type]
        config=RelayConfig(poll_interval_seconds=0.001),
    )
    task = asyncio.create_task(relay.run())
    await asyncio.wait_for(leases.resumed.wait(), timeout=0.1)
    relay.request_stop()
    await asyncio.wait_for(task, timeout=0.1)
    assert leases.calls >= 2


@pytest.mark.asyncio
async def test_relay_supervisor_retries_a_bounded_control_plane_timeout() -> None:
    class SlowThenHealthyLeases(_Leases):
        def __init__(self) -> None:
            super().__init__(())
            self.calls = 0
            self.resumed = asyncio.Event()

        async def reconcile_expired(self, session: object, **kwargs: object) -> int:
            del session, kwargs
            self.calls += 1
            if self.calls == 1:
                await asyncio.Event().wait()
            self.resumed.set()
            return 0

    leases = SlowThenHealthyLeases()
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=object(),  # type: ignore[arg-type]
        leases=leases,  # type: ignore[arg-type]
        config=RelayConfig(
            poll_interval_seconds=0.001,
            control_plane_timeout_seconds=0.01,
        ),
    )
    task = asyncio.create_task(relay.run())
    await asyncio.wait_for(leases.resumed.wait(), timeout=0.1)
    relay.request_stop()
    await asyncio.wait_for(task, timeout=0.1)
    assert leases.calls >= 2


@pytest.mark.asyncio
async def test_relay_does_not_hide_database_programming_errors() -> None:
    class BrokenLeases(_Leases):
        async def reconcile_expired(self, session: object, **kwargs: object) -> int:
            del session, kwargs
            raise ProgrammingError("bad schema", {}, RuntimeError("undefined table"))

    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=object(),  # type: ignore[arg-type]
        leases=BrokenLeases(()),  # type: ignore[arg-type]
        config=RelayConfig(poll_interval_seconds=0.001),
    )

    with pytest.raises(ProgrammingError):
        await relay.run()


@pytest.mark.asyncio
async def test_invalidated_handler_connection_isolated_without_inline_business_retry() -> None:
    now = datetime.now(UTC)
    disconnected = _claim(now)
    healthy = _claim(now)

    class Sink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            if claim.delivery.delivery_id == disconnected.delivery.delivery_id:
                raise DBAPIError(
                    "controlled",
                    {},
                    RuntimeError("connection disappeared"),
                    connection_invalidated=True,
                )

    leases = _Leases((disconnected, healthy))
    events = _Events()
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=Sink(),
        leases=leases,  # type: ignore[arg-type]
        clock=_Clock(now),
        event_sink=events,
    )

    assert await relay.run_once() == 2
    assert leases.succeeded == [healthy.delivery.delivery_id]
    assert leases.failures == []
    assert [event.kind for event in events.values] == [RuntimeEventKind.CONTROL_PLANE_FAILED]


@pytest.mark.asyncio
async def test_success_finalization_is_bounded_and_leaves_lease_recoverable() -> None:
    now = datetime.now(UTC)
    claim = _claim(now)

    class BlockedLeases(_Leases):
        async def succeed(
            self,
            session: object,
            claim: ClaimedDelivery,
            **kwargs: object,
        ) -> None:
            del session, claim, kwargs
            await asyncio.Event().wait()

    class SuccessfulSink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            del claim

    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=SuccessfulSink(),
        leases=BlockedLeases((claim,)),  # type: ignore[arg-type]
        clock=_Clock(now),
        config=RelayConfig(finalization_timeout_seconds=0.01),
    )
    started = asyncio.get_running_loop().time()
    await relay.execute_claim(claim)

    assert asyncio.get_running_loop().time() - started < 0.1


@pytest.mark.asyncio
async def test_stop_cancels_inflight_work_after_bounded_grace() -> None:
    now = datetime.now(UTC)
    claim = _claim(now, handler_timeout=1)
    admitted = asyncio.Event()
    cancelled = asyncio.Event()

    class StalledSink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            del claim
            admitted.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=StalledSink(),
        leases=_Leases((claim,)),  # type: ignore[arg-type]
        clock=_Clock(now),
        config=RelayConfig(shutdown_grace_seconds=0.01),
    )
    task = asyncio.create_task(relay.run())
    await asyncio.wait_for(admitted.wait(), timeout=0.1)
    relay.request_stop()
    await asyncio.wait_for(task, timeout=0.1)
    await asyncio.wait_for(cancelled.wait(), timeout=0.1)


@pytest.mark.asyncio
async def test_live_stalled_socket_does_not_block_next_poll_or_shutdown() -> None:
    now = datetime.now(UTC)
    claim = _claim(now, handler_timeout=0.02)
    accepted = asyncio.Event()

    async def stall(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        accepted.set()
        try:
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(stall, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    class LiveStalledSink:
        async def execute(self, claim: ClaimedDelivery) -> None:
            del claim
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                await reader.readexactly(1)
            finally:
                writer.close()
                await writer.wait_closed()

    class CyclingLeases(_Leases):
        def __init__(self) -> None:
            super().__init__((claim,))
            self.claim_calls = 0
            self.next_poll = asyncio.Event()

        async def claim(self, session: object, **kwargs: object) -> tuple[ClaimedDelivery, ...]:
            del session, kwargs
            self.claim_calls += 1
            if self.claim_calls == 1:
                return self.claims
            self.next_poll.set()
            return ()

    leases = CyclingLeases()
    relay = PollingRelay(
        sessions=_Sessions(),  # type: ignore[arg-type]
        sink=LiveStalledSink(),
        leases=leases,  # type: ignore[arg-type]
        clock=_Clock(now),
        config=RelayConfig(poll_interval_seconds=0.001),
    )
    task = asyncio.create_task(relay.run())
    try:
        await asyncio.wait_for(accepted.wait(), timeout=0.1)
        await asyncio.wait_for(leases.next_poll.wait(), timeout=0.2)
        relay.request_stop()
        await asyncio.wait_for(task, timeout=0.1)
        assert leases.failures == ["execution.timeout"]
    finally:
        relay.request_stop()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        server.close()
        await server.wait_closed()

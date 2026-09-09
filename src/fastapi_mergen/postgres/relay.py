"""Bounded polling relay; polling is the correctness path."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, TypeVar

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_mergen.core.protocols import Clock
from fastapi_mergen.core.retry import RetryPolicy, remaining_attempt_seconds
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.errors import (
    AuthorizationDenied,
    AuthorizationExpired,
    LeaseLost,
    MergenConfigurationError,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_mergen.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_mergen.observability.protocols import EventSink, NoOpEventSink, record_safely
from fastapi_mergen.postgres.errors import is_transient_database_error
from fastapi_mergen.postgres.leasing import ClaimedDelivery, LeaseRepository

_T = TypeVar("_T")


class DeliverySink(Protocol):
    async def execute(self, claim: ClaimedDelivery) -> SinkDisposition | None: ...


class SinkDisposition(StrEnum):
    COMPLETED = "completed"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class RelayConfig:
    batch_size: int = 50
    per_tenant: int = 5
    concurrency: int = 20
    poll_interval_seconds: float = 1.0
    reconcile_batch_size: int = 100
    control_plane_timeout_seconds: float = 10.0
    finalization_timeout_seconds: float = 10.0
    shutdown_grace_seconds: float = 30.0

    def __post_init__(self) -> None:
        for value in (
            self.batch_size,
            self.per_tenant,
            self.concurrency,
            self.reconcile_batch_size,
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError("Relay integer bounds must be positive.")
        if self.poll_interval_seconds <= 0 or self.poll_interval_seconds > 60:
            raise ValueError("Relay poll interval must be in (0, 60].")
        for budget in (
            self.control_plane_timeout_seconds,
            self.finalization_timeout_seconds,
            self.shutdown_grace_seconds,
        ):
            if (
                not isinstance(budget, (int, float))
                or isinstance(budget, bool)
                or budget <= 0
                or budget > 300
            ):
                raise ValueError("Relay operation budgets must be in (0, 300].")


@dataclass(slots=True)
class PollingRelay:
    sessions: async_sessionmaker[AsyncSession]
    sink: DeliverySink
    leases: LeaseRepository = field(default_factory=LeaseRepository)
    clock: Clock = field(default_factory=SystemClock)
    config: RelayConfig = field(default_factory=RelayConfig)
    event_sink: EventSink = field(default_factory=NoOpEventSink)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            cycle = asyncio.create_task(self.run_once())
            stop_waiter = asyncio.create_task(self._stop.wait())
            done, _pending = await asyncio.wait(
                (cycle, stop_waiter),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_waiter in done:
                await self._drain_cycle(cycle)
                return
            stop_waiter.cancel()
            with suppress(asyncio.CancelledError):
                await stop_waiter
            await self._finish_cycle(cycle)
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.config.poll_interval_seconds,
                )

    async def run_once(self) -> int:
        if self._stop.is_set():
            return 0
        now = self.clock.now()
        await self._control_operation(self._reconcile(now))
        if self._stop.is_set():
            return 0
        claims = await self._control_operation(self._claim())
        async with asyncio.TaskGroup() as group:
            for claim in claims:
                group.create_task(self.execute_claim(claim))
        return len(claims)

    async def execute_claim(self, claim: ClaimedDelivery) -> None:
        """Execute and finalize one already-committed lease through relay policy."""

        try:
            timeout_seconds = _remaining_claim_seconds(claim, now=self.clock.now())
            if timeout_seconds <= 0:
                raise TimeoutError
            async with asyncio.timeout(timeout_seconds):
                disposition = await self.sink.execute(claim)
        except asyncio.CancelledError:
            raise
        except PermanentDeliveryError as exc:
            await self._fail_safely(claim, exc)
        except RetryableDeliveryError as exc:
            await self._fail_safely(claim, exc)
        except (AuthorizationDenied, AuthorizationExpired):
            await self._fail_safely(
                claim,
                PermanentDeliveryError(
                    code="authorization.denied",
                    summary="Delivery authority was denied.",
                ),
            )
        except TimeoutError:
            await self._fail_safely(
                claim,
                RetryableDeliveryError(
                    code="execution.timeout",
                    summary="Delivery execution exceeded its timeout.",
                ),
            )
        except MergenConfigurationError:
            raise
        except Exception as exc:
            if is_transient_database_error(exc):
                self._record_control_failure("database.transient", claim=claim)
                return
            if isinstance(exc, DBAPIError):
                raise
            await self._fail_safely(
                claim,
                RetryableDeliveryError(
                    code="execution.failed",
                    summary="Delivery execution failed without safe classification.",
                ),
            )
        else:
            if disposition is SinkDisposition.DEFERRED:
                return
            try:
                await self._finalization_operation(self._succeed(claim))
            except LeaseLost:
                self._record_lease_lost(claim)
            except TimeoutError:
                self._record_control_failure("database.finalization_timeout", claim=claim)
            except Exception as exc:
                if not is_transient_database_error(exc):
                    raise
                self._record_control_failure("database.transient", claim=claim)

    async def _fail_safely(
        self,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
    ) -> None:
        try:
            await self._fail(claim, error)
        except LeaseLost:
            self._record_lease_lost(claim)
        except TimeoutError:
            self._record_control_failure("database.finalization_timeout", claim=claim)
        except Exception as exc:
            if not is_transient_database_error(exc):
                raise
            self._record_control_failure("database.transient", claim=claim)

    async def _fail(
        self,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
    ) -> None:
        await self._finalization_operation(self._fail_in_session(claim, error))

    async def _reconcile(self, now: datetime) -> None:
        async with self.sessions() as session:
            await self.leases.reconcile_expired(
                session,
                now=now,
                batch_size=self.config.reconcile_batch_size,
            )

    async def _claim(self) -> tuple[ClaimedDelivery, ...]:
        async with self.sessions() as session:
            return await self.leases.claim(
                session,
                now=self.clock.now(),
                # A lease starts when claim() commits, not when a semaphore later
                # admits the sink. Never lease more than can begin immediately.
                batch_size=min(self.config.batch_size, self.config.concurrency),
                per_tenant=self.config.per_tenant,
            )

    async def _succeed(self, claim: ClaimedDelivery) -> None:
        async with self.sessions() as session:
            await self.leases.succeed(session, claim, now=self.clock.now())

    async def _fail_in_session(
        self,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
    ) -> None:
        async with self.sessions() as session:
            await self.leases.fail(
                session,
                claim,
                error,
                now=self.clock.now(),
                retry_after=(
                    error.retry_after if isinstance(error, RetryableDeliveryError) else None
                ),
            )

    async def _control_operation(self, operation: Awaitable[_T]) -> _T:
        async with asyncio.timeout(self.config.control_plane_timeout_seconds):
            return await operation

    async def _finalization_operation(self, operation: Awaitable[_T]) -> _T:
        async with asyncio.timeout(self.config.finalization_timeout_seconds):
            return await operation

    async def _drain_cycle(self, cycle: asyncio.Task[int]) -> None:
        if not cycle.done():
            done, _pending = await asyncio.wait(
                (cycle,),
                timeout=self.config.shutdown_grace_seconds,
            )
            if not done:
                cycle.cancel()
                # Cooperative database/network operations receive cancellation. Do
                # not let cancellation-suppressing code defeat the relay's own grace;
                # the external supervisor owns hard process termination after return.
                cycle.add_done_callback(_consume_task_result)
                return
        await self._finish_cycle(cycle)

    async def _finish_cycle(self, cycle: asyncio.Task[int]) -> None:
        try:
            await cycle
        except TimeoutError:
            self._record_control_failure("database.control_timeout")
        except Exception as exc:
            # A supervisor loop survives reviewed transient outages;
            # committed leases remain recoverable after expiry.
            if not is_transient_database_error(exc):
                raise
            self._record_control_failure("database.transient")

    def _record_control_failure(
        self,
        code: str,
        *,
        claim: ClaimedDelivery | None = None,
    ) -> None:
        record_safely(
            self.event_sink,
            RuntimeEvent(
                RuntimeEventKind.CONTROL_PLANE_FAILED,
                self.clock.now(),
                {
                    "failure.code": code,
                    "destination.kind": (
                        claim.delivery.destination_kind if claim is not None else "control"
                    ),
                },
                TraceLineage(
                    event_id=claim.event.event_id if claim is not None else None,
                    delivery_id=claim.delivery.delivery_id if claim is not None else None,
                    attempt_id=claim.attempt.attempt_id if claim is not None else None,
                    replay_of=claim.delivery.replay_of if claim is not None else None,
                    traceparent=claim.event.traceparent if claim is not None else None,
                ),
            ),
        )

    def _record_lease_lost(self, claim: ClaimedDelivery) -> None:
        record_safely(
            self.event_sink,
            RuntimeEvent(
                RuntimeEventKind.LEASE_LOST,
                self.clock.now(),
                {"destination.kind": claim.delivery.destination_kind},
                TraceLineage(
                    event_id=claim.event.event_id,
                    delivery_id=claim.delivery.delivery_id,
                    attempt_id=claim.attempt.attempt_id,
                    replay_of=claim.delivery.replay_of,
                    traceparent=claim.event.traceparent,
                ),
            ),
        )


def _remaining_claim_seconds(claim: ClaimedDelivery, *, now: datetime) -> float:
    retry = claim.route_snapshot.get("retry")
    lease_expires_at = claim.delivery.lease_expires_at
    if not isinstance(retry, dict) or lease_expires_at is None:
        raise MergenConfigurationError("Claim attempt deadline is invalid.")
    policy = RetryPolicy.from_dict(retry)
    return remaining_attempt_seconds(
        policy=policy,
        delivery_created_at=claim.delivery.created_at,
        attempt_started_at=claim.attempt.started_at,
        lease_expires_at=lease_expires_at,
        now=now,
    )


def _consume_task_result(task: asyncio.Task[object]) -> None:
    if task.cancelled():
        return
    with suppress(Exception):
        task.result()


__all__ = ["DeliverySink", "PollingRelay", "RelayConfig", "SinkDisposition"]

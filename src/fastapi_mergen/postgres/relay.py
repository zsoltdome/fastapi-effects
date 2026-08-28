"""Bounded polling relay; polling is the correctness path."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy.exc import InterfaceError, OperationalError
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
from fastapi_mergen.postgres.leasing import ClaimedDelivery, LeaseRepository


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
            # A supervisor loop survives transient database outages; committed
            # leases remain recoverable after expiry.
            with suppress(OperationalError, InterfaceError):
                await self.run_once()
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.config.poll_interval_seconds,
                )

    async def run_once(self) -> int:
        if self._stop.is_set():
            return 0
        now = self.clock.now()
        async with self.sessions() as session:
            await self.leases.reconcile_expired(
                session,
                now=now,
                batch_size=self.config.reconcile_batch_size,
            )
        if self._stop.is_set():
            return 0
        async with self.sessions() as session:
            claims = await self.leases.claim(
                session,
                now=self.clock.now(),
                # A lease starts when claim() commits, not when a semaphore later
                # admits the sink.  Never lease more work than this relay can begin
                # immediately or queued claims can expire before their first I/O.
                batch_size=min(self.config.batch_size, self.config.concurrency),
                per_tenant=self.config.per_tenant,
            )
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
        except Exception:
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
                async with self.sessions() as session:
                    await self.leases.succeed(session, claim, now=self.clock.now())
            except LeaseLost:
                self._record_lease_lost(claim)
            except (OperationalError, InterfaceError):
                return

    async def _fail_safely(
        self,
        claim: ClaimedDelivery,
        error: RetryableDeliveryError | PermanentDeliveryError,
    ) -> None:
        try:
            await self._fail(claim, error)
        except LeaseLost:
            self._record_lease_lost(claim)
        except (OperationalError, InterfaceError):
            return

    async def _fail(
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


__all__ = ["DeliverySink", "PollingRelay", "RelayConfig", "SinkDisposition"]

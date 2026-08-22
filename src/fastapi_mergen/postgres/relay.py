"""Bounded polling relay; polling is the correctness path."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_mergen.core.protocols import Clock
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.errors import (
    AuthorizationDenied,
    AuthorizationExpired,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
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
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
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
            disposition = await self.sink.execute(claim)
        except asyncio.CancelledError:
            raise
        except PermanentDeliveryError as exc:
            await self._fail(claim, exc)
        except RetryableDeliveryError as exc:
            await self._fail(claim, exc)
        except (AuthorizationDenied, AuthorizationExpired):
            await self._fail(
                claim,
                PermanentDeliveryError(
                    code="authorization.denied",
                    summary="Delivery authority was denied.",
                ),
            )
        except TimeoutError:
            await self._fail(
                claim,
                RetryableDeliveryError(
                    code="execution.timeout",
                    summary="Delivery execution exceeded its timeout.",
                ),
            )
        except Exception:
            await self._fail(
                claim,
                RetryableDeliveryError(
                    code="execution.failed",
                    summary="Delivery execution failed without safe classification.",
                ),
            )
        else:
            if disposition is SinkDisposition.DEFERRED:
                return
            async with self.sessions() as session:
                await self.leases.succeed(session, claim, now=self.clock.now())

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


__all__ = ["DeliverySink", "PollingRelay", "RelayConfig", "SinkDisposition"]

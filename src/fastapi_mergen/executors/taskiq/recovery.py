"""Bounded periodic recovery for ambiguous or expired Taskiq handoffs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_mergen.core.protocols import Clock
from fastapi_mergen.core.runtime import SystemClock
from fastapi_mergen.executors.taskiq.store import TaskiqHandoffStore


@dataclass(slots=True)
class TaskiqRecovery:
    sessions: async_sessionmaker[AsyncSession]
    store: TaskiqHandoffStore = field(default_factory=TaskiqHandoffStore)
    clock: Clock = field(default_factory=SystemClock)
    enqueue_timeout: timedelta = timedelta(minutes=5)
    batch_size: int = 100

    async def run_once(self) -> int:
        async with self.sessions() as session:
            return await self.store.recover_expired(
                session,
                now=self.clock.now(),
                enqueue_timeout=self.enqueue_timeout,
                batch_size=self.batch_size,
            )


__all__ = ["TaskiqRecovery"]

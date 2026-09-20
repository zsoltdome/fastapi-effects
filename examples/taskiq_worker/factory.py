"""Host-facing composition helper for one FastAPIEffects Taskiq bridge task."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_effects.executors.protocols import HandoffExecutor
from fastapi_effects.executors.taskiq.adapter import register_taskiq_bridge
from fastapi_effects.executors.taskiq.store import TaskiqHandoffStore
from fastapi_effects.executors.taskiq.worker import TaskiqWorkerBridge


def register_worker(
    *,
    broker: Any,
    relay_sessions: async_sessionmaker[AsyncSession],
    executor: HandoffExecutor,
) -> Any:
    """Register on both sender and worker processes during application startup."""
    store = TaskiqHandoffStore()
    worker = TaskiqWorkerBridge(
        sessions=relay_sessions,
        executor=executor,
        store=store,
    )
    return register_taskiq_bridge(broker, worker)

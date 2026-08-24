"""Taskiq worker-process fixture used by the real executor conformance adapter."""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from taskiq_redis import RedisStreamBroker

from fastapi_mergen.core.principal import Principal
from fastapi_mergen.executors.taskiq.adapter import register_taskiq_bridge
from fastapi_mergen.executors.taskiq.store import TaskiqHandoffStore
from fastapi_mergen.executors.taskiq.worker import TaskiqWorkerBridge
from fastapi_mergen.postgres.leasing import ClaimedDelivery


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Taskiq worker fixture requires {name}.")
    return value


class _ProcessBoundaryExecutor:
    async def execute(self, claim: ClaimedDelivery) -> None:
        parent_pid = int(_required_environment("MERGEN_TASKIQ_PARENT_PID"))
        if os.getpid() == parent_pid:
            raise AssertionError("Taskiq handler did not cross a process boundary.")
        principal = Principal.from_envelope(claim.event.principal)
        if principal.tenant_id != claim.delivery.tenant_id:
            raise AssertionError("Taskiq worker lost tenant continuity.")


engine = create_async_engine(_required_environment("MERGEN_TASKIQ_RELAY_DSN"))
sessions = async_sessionmaker(engine, expire_on_commit=False)
broker = RedisStreamBroker(
    url=_required_environment("MERGEN_TASKIQ_REDIS_URL"),
    queue_name=_required_environment("MERGEN_TASKIQ_QUEUE_NAME"),
    consumer_group_name=f"{_required_environment('MERGEN_TASKIQ_QUEUE_NAME')}-workers",
    xread_block=100,
    idle_timeout=30_000,
)
worker = TaskiqWorkerBridge(
    sessions=sessions,
    executor=_ProcessBoundaryExecutor(),
    store=TaskiqHandoffStore(),
)
execute_handoff = register_taskiq_bridge(broker, worker)

__all__ = ["broker", "execute_handoff"]

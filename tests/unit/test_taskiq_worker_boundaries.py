from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest

from fastapi_effects.executors.taskiq.envelope import TaskiqHandoffEnvelope
from fastapi_effects.executors.taskiq.worker import TaskiqWorkerBridge


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        del args


class _Sessions:
    def __call__(self) -> _SessionContext:
        return _SessionContext()


class _BlockedStore:
    async def claim_execution(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        await asyncio.Event().wait()


class _Executor:
    async def execute(self, claim: object) -> None:
        del claim


@pytest.mark.asyncio
async def test_taskiq_control_plane_admission_is_bounded() -> None:
    attempt_id = uuid4()
    envelope = TaskiqHandoffEnvelope(
        tenant_id=uuid4(),
        handoff_id=uuid4(),
        delivery_id=uuid4(),
        attempt_id=attempt_id,
        task_id=f"fastapi_effects_{attempt_id}",
        handoff_token=uuid4(),
    )
    worker = TaskiqWorkerBridge(
        sessions=_Sessions(),  # type: ignore[arg-type]
        executor=_Executor(),
        store=_BlockedStore(),  # type: ignore[arg-type]
        control_plane_timeout=timedelta(milliseconds=10),
    )

    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        await worker.execute(envelope.to_dict())
    assert asyncio.get_running_loop().time() - started < 0.1

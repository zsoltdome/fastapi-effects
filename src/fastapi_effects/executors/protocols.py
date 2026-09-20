"""Executor-neutral durable handoff contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from fastapi_effects.postgres.leasing import ClaimedDelivery


class HandoffState(StrEnum):
    PREPARED = "prepared"
    ENQUEUED = "enqueued"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    RETRY_WAIT = "retry_wait"
    DEAD = "dead"


class HandoffExecutor(Protocol):
    """Execute application code from a durable FastAPIEffects delivery claim."""

    async def execute(self, claim: ClaimedDelivery) -> None: ...


__all__ = ["HandoffExecutor", "HandoffState"]

"""Durable external-executor contracts."""

from fastapi_mergen.executors.protocols import HandoffExecutor, HandoffState

__all__ = ["HandoffExecutor", "HandoffState"]

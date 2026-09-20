"""Durable external-executor contracts."""

from fastapi_effects.executors.protocols import HandoffExecutor, HandoffState

__all__ = ["HandoffExecutor", "HandoffState"]

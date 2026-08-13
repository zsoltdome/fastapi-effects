"""Dependency-free vendor-neutral runtime telemetry protocol."""

from __future__ import annotations

from typing import Protocol

from fastapi_mergen.observability.events import RuntimeEvent


class EventSink(Protocol):
    def record(self, event: RuntimeEvent) -> None: ...


class NoOpEventSink:
    def record(self, event: RuntimeEvent) -> None:
        del event


def record_safely(sink: EventSink, event: RuntimeEvent) -> None:
    """Prevent telemetry backends from changing runtime correctness."""

    try:
        sink.record(event)
    except Exception:
        return


__all__ = ["EventSink", "NoOpEventSink", "record_safely"]

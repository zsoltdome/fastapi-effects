"""Dependency-free secret-minimizing runtime observability."""

from fastapi_mergen.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_mergen.observability.logging import StructuredLogEventSink
from fastapi_mergen.observability.protocols import EventSink, NoOpEventSink

__all__ = [
    "EventSink",
    "NoOpEventSink",
    "RuntimeEvent",
    "RuntimeEventKind",
    "StructuredLogEventSink",
    "TraceLineage",
]

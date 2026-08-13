"""Adapter from token-free delegation audit events to runtime telemetry."""

from __future__ import annotations

from fastapi_mergen.delegation.audit import DelegationAuditEvent, DelegationAuditOutcome
from fastapi_mergen.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_mergen.observability.protocols import EventSink, record_safely

_KINDS = {
    DelegationAuditOutcome.ISSUED: RuntimeEventKind.DELEGATION_ISSUED,
    DelegationAuditOutcome.ALLOWED: RuntimeEventKind.DELEGATION_ALLOWED,
    DelegationAuditOutcome.DENIED: RuntimeEventKind.DELEGATION_DENIED,
}


class DelegationTelemetrySink:
    def __init__(self, sink: EventSink) -> None:
        self._sink = sink

    def record(self, event: DelegationAuditEvent) -> None:
        kind = _KINDS.get(event.outcome)
        if kind is None:
            return
        record_safely(
            self._sink,
            RuntimeEvent(
                kind=kind,
                occurred_at=event.occurred_at,
                attributes={
                    "authorization.result": event.outcome.value,
                    "capability": "delegation",
                },
                lineage=TraceLineage(delegation_id=event.token_id),
            ),
        )


__all__ = ["DelegationTelemetrySink"]

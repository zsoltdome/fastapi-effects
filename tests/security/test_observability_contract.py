from __future__ import annotations

import logging
from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_mergen.observability.logging import StructuredLogEventSink
from fastapi_mergen.observability.otel import OpenTelemetryEventSink
from fastapi_mergen.observability.protocols import record_safely


class Instrument:
    def __init__(self) -> None:
        self.records: list[tuple[float, dict[str, object]]] = []

    def add(self, value: float, *, attributes: dict[str, object]) -> None:
        self.records.append((value, attributes))

    def record(self, value: float, *, attributes: dict[str, object]) -> None:
        self.records.append((value, attributes))


class Meter:
    def __init__(self) -> None:
        self.counter = Instrument()
        self.histogram = Instrument()
        self.backlog = Instrument()

    def create_counter(self, name: str) -> Instrument:
        assert name == "fastapi_mergen.runtime.events"
        return self.counter

    def create_histogram(self, name: str, *, unit: str) -> Instrument:
        if name == "fastapi_mergen.operation.duration":
            assert unit == "ms"
            return self.histogram
        assert (name, unit) == ("fastapi_mergen.backlog.oldest_age", "s")
        return self.backlog


class Tracer:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def start_as_current_span(
        self,
        name: str,
        *,
        attributes: dict[str, object],
    ) -> nullcontext[None]:
        assert name == "fastapi_mergen.succeeded"
        self.attributes = attributes
        return nullcontext()


class BrokenSink:
    def record(self, event: RuntimeEvent) -> None:
        del event
        raise RuntimeError("telemetry backend failed")


def test_metrics_exclude_lineage_and_traces_retain_it() -> None:
    meter = Meter()
    tracer = Tracer()
    delivery_id = uuid4()
    event = RuntimeEvent(
        RuntimeEventKind.SUCCEEDED,
        datetime.now(UTC),
        {"destination.kind": "webhook", "duration.ms": 12.5},
        TraceLineage(delivery_id=delivery_id),
    )
    OpenTelemetryEventSink(meter, tracer).record(event)
    metric_attributes = meter.counter.records[0][1]
    assert "mergen.delivery.id" not in metric_attributes
    assert tracer.attributes["mergen.delivery.id"] == str(delivery_id)
    assert meter.histogram.records[0][0] == 12.5


def test_secret_payload_fields_are_rejected_before_logs_metrics_or_traces(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "observability-canary-never-emit"
    for key in ("payload", "body", "secret", "message", "tenant.id"):
        with pytest.raises(MergenConfigurationError, match="unsafe"):
            RuntimeEvent(RuntimeEventKind.DEAD, datetime.now(UTC), {key: canary})
    logger = logging.getLogger("fastapi_mergen.test.observability")
    with caplog.at_level(logging.INFO, logger=logger.name):
        StructuredLogEventSink(logger).record(
            RuntimeEvent(
                RuntimeEventKind.DEAD,
                datetime.now(UTC),
                {"failure.code": "remote.rejected"},
            )
        )
    assert canary not in caplog.text


def test_observability_backend_failure_never_changes_control_flow() -> None:
    event = RuntimeEvent(RuntimeEventKind.PUBLISHED, datetime.now(UTC), {})
    assert record_safely(BrokenSink(), event) is None

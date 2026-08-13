"""Lazy OpenTelemetry mapping; importing core never imports the SDK."""

from __future__ import annotations

from typing import Any

from fastapi_mergen._optional import require_modules
from fastapi_mergen.observability.events import RuntimeEvent

_METRIC_LABELS = frozenset(
    {
        "authorization.result",
        "auto_paused",
        "capability",
        "destination.kind",
        "outcome",
        "state",
    }
)


class OpenTelemetryEventSink:
    def __init__(self, meter: Any, tracer: Any | None = None) -> None:
        self._counter = meter.create_counter("fastapi_mergen.runtime.events")
        self._duration = meter.create_histogram(
            "fastapi_mergen.operation.duration",
            unit="ms",
        )
        self._backlog_age = meter.create_histogram(
            "fastapi_mergen.backlog.oldest_age",
            unit="s",
        )
        self._tracer = tracer

    def record(self, event: RuntimeEvent) -> None:
        metric_attributes: dict[str, str | int | float | bool] = {
            "mergen.event.kind": event.kind.value,
            **{
                f"mergen.{key}": value
                for key, value in event.attributes.items()
                if key in _METRIC_LABELS
            },
        }
        try:
            self._counter.add(1, attributes=metric_attributes)
            duration = event.attributes.get("duration.ms")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                self._duration.record(float(duration), attributes=metric_attributes)
            backlog_age = event.attributes.get("backlog.age.seconds")
            if isinstance(backlog_age, (int, float)) and not isinstance(backlog_age, bool):
                self._backlog_age.record(float(backlog_age), attributes=metric_attributes)
            if self._tracer is not None:
                span_attributes = {
                    **metric_attributes,
                    **{f"mergen.{key}": value for key, value in event.attributes.items()},
                    **{f"mergen.{key}": value for key, value in event.lineage.attributes().items()},
                }
                with self._tracer.start_as_current_span(
                    f"fastapi_mergen.{event.kind.value}",
                    attributes=span_attributes,
                ):
                    pass
        except Exception:
            return


def create_otel_sink(name: str = "fastapi_mergen") -> OpenTelemetryEventSink:
    require_modules(
        feature="OpenTelemetry observability",
        extra="otel",
        modules=("opentelemetry",),
    )
    from opentelemetry import metrics, trace

    return OpenTelemetryEventSink(metrics.get_meter(name), trace.get_tracer(name))


__all__ = ["OpenTelemetryEventSink", "create_otel_sink"]

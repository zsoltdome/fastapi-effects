"""Secret-minimizing JSON logging sink using the standard library."""

from __future__ import annotations

import json
import logging

from fastapi_effects.observability.events import RuntimeEvent


class StructuredLogEventSink:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("fastapi_effects.runtime")

    def record(self, event: RuntimeEvent) -> None:
        payload = {
            "event": f"fastapi_effects.{event.kind.value}",
            "occurred_at": event.occurred_at.isoformat(),
            "attributes": dict(event.attributes),
            "lineage": dict(event.lineage.attributes()),
        }
        try:
            self._logger.info("%s", json.dumps(payload, sort_keys=True, separators=(",", ":")))
        except Exception:
            return


__all__ = ["StructuredLogEventSink"]

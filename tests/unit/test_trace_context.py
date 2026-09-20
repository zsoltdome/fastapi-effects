from __future__ import annotations

import pytest

from fastapi_effects import Event
from fastapi_effects.errors import FastAPIEffectsConfigurationError


def test_w3c_trace_context_accepts_bounded_valid_values() -> None:
    event = Event(
        type="invoice.created",
        version=1,
        data={},
        traceparent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        tracestate="vendor=value,other=opaque==",
    )
    assert event.tracestate == "vendor=value,other=opaque=="


@pytest.mark.parametrize(
    "traceparent",
    [
        "00-short-bbbbbbbbbbbbbbbb-01",
        "00-00000000000000000000000000000000-bbbbbbbbbbbbbbbb-01",
        "ff-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        "00-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA-bbbbbbbbbbbbbbbb-01",
    ],
)
def test_malformed_traceparent_is_rejected(traceparent: str) -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="traceparent"):
        Event(type="invoice.created", version=1, data={}, traceparent=traceparent)


@pytest.mark.parametrize("tracestate", ["duplicate=a,duplicate=b", "a=", "A=value"])
def test_malformed_tracestate_is_rejected(tracestate: str) -> None:
    with pytest.raises(FastAPIEffectsConfigurationError, match="tracestate"):
        Event(type="invoice.created", version=1, data={}, tracestate=tracestate)

from __future__ import annotations

import pytest
from starlette.responses import Response, StreamingResponse

from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.idempotency.responses import CapturedResponse, capture_response


def test_safe_response_round_trips_and_marks_replay() -> None:
    original = Response(
        b'{"invoice":"inv-1"}',
        status_code=201,
        media_type="application/json",
        headers={"ETag": '"invoice-v1"', "Cache-Control": "private"},
    )
    captured = capture_response(original)
    replay = captured.to_response(replayed=True)
    assert replay.status_code == 201
    assert replay.body == original.body
    assert replay.headers["content-type"] == original.headers["content-type"]
    assert replay.headers["etag"] == '"invoice-v1"'
    assert replay.headers["idempotency-replayed"] == "true"


@pytest.mark.parametrize(
    "headers",
    [
        {"Set-Cookie": "session=secret"},
        {"WWW-Authenticate": "Bearer secret"},
        {"Connection": "close"},
        {"ETag": '"ok"\r\nX-Injected: yes'},
    ],
)
def test_unsafe_response_headers_are_rejected(headers: dict[str, str]) -> None:
    with pytest.raises((MergenConfigurationError, ValueError)):
        capture_response(Response(b"ok", media_type="text/plain", headers=headers))


def test_streaming_and_oversized_responses_are_rejected() -> None:
    with pytest.raises(MergenConfigurationError):
        capture_response(StreamingResponse(iter((b"chunk",)), media_type="text/plain"))
    with pytest.raises(MergenConfigurationError):
        CapturedResponse(
            status_code=200,
            media_type="text/plain",
            body=b"x" * (256 * 1024 + 1),
        )

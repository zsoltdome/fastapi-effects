from __future__ import annotations

import asyncio

import pytest

from fastapi_mergen.errors import RetryableDeliveryError
from fastapi_mergen.webhooks.http11 import ResponseLimits, parse_response

pytestmark = pytest.mark.security


def _reader(value: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader(limit=4096)
    reader.feed_data(value)
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
async def test_chunked_response_consumes_terminal_chunk_and_trailers() -> None:
    response = await parse_response(
        _reader(
            b"HTTP/1.1 503 Unavailable\r\n"
            b"Transfer-Encoding: chunked\r\nRetry-After: 3\r\n\r\n"
            b"4\r\nnope\r\n0\r\nX-Trailer: discarded\r\n\r\n"
        ),
        limits=ResponseLimits(),
    )
    assert response.status_code == 503
    assert response.discarded_body_bytes == 4
    assert response.headers["retry-after"] == "3"


@pytest.mark.asyncio
async def test_oversized_body_is_rejected_without_retention() -> None:
    with pytest.raises(RetryableDeliveryError, match=r"webhook\.response_bounds"):
        await parse_response(
            _reader(b"HTTP/1.1 500 Nope\r\nContent-Length: 9\r\n\r\ncontrolled"),
            limits=ResponseLimits(maximum_body_bytes=8),
        )

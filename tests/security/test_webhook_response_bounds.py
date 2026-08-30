from __future__ import annotations

import asyncio

import pytest

from fastapi_mergen.errors import PermanentDeliveryError, RetryableDeliveryError
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("informational", "final_status"),
    [
        (b"HTTP/1.1 100 Continue\r\n\r\n", 204),
        (b"HTTP/1.1 103 Early Hints\r\nLink: </x>; rel=preload\r\n\r\n", 200),
    ],
)
async def test_informational_responses_are_consumed_before_final_response(
    informational: bytes,
    final_status: int,
) -> None:
    response = await parse_response(
        _reader(
            informational + f"HTTP/1.1 {final_status} Final\r\nContent-Length: 0\r\n\r\n".encode()
        ),
        limits=ResponseLimits(),
    )
    assert response.status_code == final_status


@pytest.mark.asyncio
async def test_informational_response_count_uses_an_aggregate_bound() -> None:
    value = b"HTTP/1.1 100 Continue\r\n\r\n" * 3
    value += b"HTTP/1.1 204 Final\r\n\r\n"
    with pytest.raises(RetryableDeliveryError, match=r"webhook\.response_bounds"):
        await parse_response(
            _reader(value),
            limits=ResponseLimits(maximum_informational_responses=2),
        )


@pytest.mark.asyncio
async def test_protocol_upgrade_is_explicitly_unsupported() -> None:
    with pytest.raises(PermanentDeliveryError, match=r"protocol_upgrade_unsupported"):
        await parse_response(
            _reader(b"HTTP/1.1 101 Switching Protocols\r\nConnection: upgrade\r\n\r\n"),
            limits=ResponseLimits(),
        )


@pytest.mark.asyncio
async def test_eof_after_informational_response_is_not_success() -> None:
    with pytest.raises(RetryableDeliveryError, match=r"webhook\.response_bounds"):
        await parse_response(
            _reader(b"HTTP/1.1 103 Early Hints\r\n\r\n"),
            limits=ResponseLimits(),
        )

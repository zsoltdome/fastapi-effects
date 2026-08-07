from __future__ import annotations

import asyncio
import ssl
from typing import Any

import pytest

from fastapi_mergen.webhooks.address_policy import parse_endpoint
from fastapi_mergen.webhooks.transport import ExplicitIPTransport

pytestmark = pytest.mark.security


class _Writer:
    def __init__(self) -> None:
        self.request = b""

    def write(self, value: bytes) -> None:
        self.request += value

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


@pytest.mark.asyncio
async def test_transport_connects_ip_but_preserves_sni_and_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _Writer()
    observed: dict[str, Any] = {}

    async def open_connection(**kwargs: Any) -> tuple[asyncio.StreamReader, _Writer]:
        observed.update(kwargs)
        reader = asyncio.StreamReader()
        reader.feed_data(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
        reader.feed_eof()
        return reader, writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    endpoint = parse_endpoint(
        "https://customer.example/hooks",
        production=False,
        allowed_ports=frozenset({443}),
    )
    transport = ExplicitIPTransport(
        production=False,
        ssl_context=ssl.create_default_context(),
    )
    result = await transport.send(
        endpoint=endpoint,
        connected_ip="127.0.0.1",
        body=b"{}",
        headers={"webhook-id": "msg_1"},
    )

    assert observed["host"] == "127.0.0.1"
    assert observed["server_hostname"] == "customer.example"
    assert b"Host: customer.example\r\n" in writer.request
    assert result.connected_ip == "127.0.0.1"

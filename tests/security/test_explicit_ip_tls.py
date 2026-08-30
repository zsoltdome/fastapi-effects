from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.webhooks.address_policy import parse_endpoint
from fastapi_mergen.webhooks.transport import ExplicitIPTransport, TransportLimits

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


def test_production_transport_rejects_insecure_supplied_context() -> None:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with pytest.raises(MergenConfigurationError, match="certificate and hostname"):
        ExplicitIPTransport(production=True, ssl_context=context)


@pytest.mark.asyncio
async def test_mutated_production_context_is_revalidated_before_io() -> None:
    opened = False

    async def open_connection(**kwargs: Any) -> tuple[asyncio.StreamReader, _Writer]:
        nonlocal opened
        del kwargs
        opened = True
        raise AssertionError("insecure context reached I/O")

    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    transport = ExplicitIPTransport(
        production=True,
        ssl_context=context,
        connection_opener=open_connection,
    )
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    endpoint = parse_endpoint(
        "https://customer.example/hooks",
        production=True,
        allowed_ports=frozenset({443}),
    )
    with pytest.raises(MergenConfigurationError, match="certificate and hostname"):
        await transport.send(
            endpoint=endpoint,
            connected_ip="8.8.8.8",
            body=b"{}",
            headers={"webhook-id": "msg_1"},
        )
    assert not opened


@pytest.mark.asyncio
async def test_transport_close_is_bounded_by_total_timeout() -> None:
    class HangingWriter(_Writer):
        async def wait_closed(self) -> None:
            await asyncio.Event().wait()

    async def open_connection(**kwargs: Any) -> tuple[asyncio.StreamReader, HangingWriter]:
        del kwargs
        reader = asyncio.StreamReader()
        reader.feed_data(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
        reader.feed_eof()
        return reader, HangingWriter()

    endpoint = parse_endpoint(
        "https://customer.example/hooks",
        production=False,
        allowed_ports=frozenset({443}),
    )
    transport = ExplicitIPTransport(
        production=False,
        limits=TransportLimits(
            connect_timeout_seconds=0.02,
            write_timeout_seconds=0.02,
            total_timeout_seconds=0.02,
        ),
        connection_opener=open_connection,
    )
    started = asyncio.get_running_loop().time()
    result = await transport.send(
        endpoint=endpoint,
        connected_ip="127.0.0.1",
        body=b"{}",
        headers={"webhook-id": "msg_1"},
    )
    assert asyncio.get_running_loop().time() - started < 0.1
    assert result.response.status_code == 204


@pytest.mark.asyncio
async def test_custom_ca_keeps_hostname_verification_and_original_sni(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "customer.example")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("customer.example")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM)
    certificate_path = tmp_path / "server.pem"
    key_path = tmp_path / "server.key"
    certificate_path.write_bytes(certificate_pem)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    observed: dict[str, str | None] = {}
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificate_path, key_path)

    def record_sni(
        ssl_object: ssl.SSLObject,
        server_name: str | None,
        context: ssl.SSLContext,
    ) -> None:
        del ssl_object, context
        observed["server_name"] = server_name

    server_context.set_servername_callback(record_sni)

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        content_length = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                content_length = int(line.partition(b":")[2].strip())
        if content_length:
            await reader.readexactly(content_length)
        writer.write(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(receive, "127.0.0.1", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]
    client_context = ssl.create_default_context(cadata=certificate_pem.decode("ascii"))
    client_context.minimum_version = ssl.TLSVersion.TLSv1_2
    monkeypatch.setattr(
        "fastapi_mergen.webhooks.transport.validate_public_addresses",
        lambda values: tuple(values),
    )
    endpoint = parse_endpoint(
        f"https://customer.example:{port}/hooks",
        production=False,
        allowed_ports=frozenset({port}),
    )
    try:
        result = await ExplicitIPTransport(
            production=True,
            ssl_context=client_context,
        ).send(
            endpoint=endpoint,
            connected_ip="127.0.0.1",
            body=b"{}",
            headers={"webhook-id": "msg_custom_ca"},
        )
    finally:
        server.close()
        await server.wait_closed()

    assert result.response.status_code == 204
    assert observed == {"server_name": "customer.example"}

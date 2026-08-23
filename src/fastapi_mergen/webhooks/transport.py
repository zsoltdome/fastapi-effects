"""Attempt-time DNS validation and explicit-IP TLS HTTP transport."""

from __future__ import annotations

import asyncio
import socket
import ssl
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Protocol

from fastapi_mergen.errors import (
    MergenConfigurationError,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from fastapi_mergen.webhooks.address_policy import (
    EndpointTarget,
    parse_endpoint,
    validate_public_addresses,
)
from fastapi_mergen.webhooks.http11 import (
    HttpResponseMetadata,
    ResponseLimits,
    parse_response,
)


class AddressResolver(Protocol):
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]: ...


class ConnectionOpener(Protocol):
    async def __call__(
        self,
        *,
        host: str,
        port: int,
        ssl: ssl.SSLContext | None,
        server_hostname: str | None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]: ...


class SystemAddressResolver:
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        try:
            answers = await loop.getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except OSError as exc:
            raise RetryableDeliveryError(
                code="webhook.dns_failed",
                summary="Webhook endpoint DNS resolution failed.",
            ) from exc
        return tuple(dict.fromkeys(str(answer[4][0]) for answer in answers))


@dataclass(frozen=True, slots=True)
class TransportLimits:
    connect_timeout_seconds: float = 5.0
    write_timeout_seconds: float = 10.0
    total_timeout_seconds: float = 30.0
    maximum_request_bytes: int = 512 * 1024
    maximum_redirects: int = 0
    response: ResponseLimits = field(default_factory=ResponseLimits)

    def __post_init__(self) -> None:
        if not 0 < self.connect_timeout_seconds <= self.total_timeout_seconds <= 300:
            raise ValueError("Webhook connect/total timeouts are invalid.")
        if not 0 < self.write_timeout_seconds <= self.total_timeout_seconds:
            raise ValueError("Webhook write timeout is invalid.")
        if not isinstance(self.maximum_request_bytes, int) or self.maximum_request_bytes < 1:
            raise ValueError("Webhook maximum request size must be positive.")
        if (
            not isinstance(self.maximum_redirects, int)
            or isinstance(self.maximum_redirects, bool)
            or not 0 <= self.maximum_redirects <= 5
        ):
            raise ValueError("Webhook redirect limit must be in [0, 5].")


@dataclass(frozen=True, slots=True)
class TransportResult:
    connected_ip: str
    response: HttpResponseMetadata


class ExplicitIPTransport:
    """Open exactly the validated IP; retain hostname for TLS SNI and Host."""

    def __init__(
        self,
        *,
        limits: TransportLimits | None = None,
        ssl_context: ssl.SSLContext | None = None,
        production: bool = True,
        connection_opener: ConnectionOpener | None = None,
    ) -> None:
        self._limits = limits or TransportLimits()
        self._production = production
        self._ssl_context = ssl_context or _secure_ssl_context()
        self._connection_opener = connection_opener or asyncio.open_connection

    @property
    def limits(self) -> TransportLimits:
        """Return the immutable transport policy used for this client."""
        return self._limits

    async def send(
        self,
        *,
        endpoint: EndpointTarget,
        connected_ip: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> TransportResult:
        approved = (
            validate_public_addresses([connected_ip])[0] if self._production else connected_ip
        )
        request = _request_bytes(endpoint=endpoint, body=body, headers=headers)
        if len(request) > self._limits.maximum_request_bytes:
            raise PermanentDeliveryError(
                code="webhook.request_oversized",
                summary="Webhook request exceeded its configured byte limit.",
            )
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self._limits.total_timeout_seconds):
                use_tls = endpoint.scheme == "https"
                reader, connected_writer = await asyncio.wait_for(
                    self._connection_opener(
                        host=approved,
                        port=endpoint.port,
                        ssl=self._ssl_context if use_tls else None,
                        server_hostname=endpoint.hostname if use_tls else None,
                    ),
                    timeout=self._limits.connect_timeout_seconds,
                )
                writer = connected_writer
                writer.write(request)
                await asyncio.wait_for(
                    writer.drain(),
                    timeout=self._limits.write_timeout_seconds,
                )
                response = await parse_response(reader, limits=self._limits.response)
                return TransportResult(connected_ip=approved, response=response)
        except (ssl.SSLError, OSError, TimeoutError) as exc:
            raise RetryableDeliveryError(
                code="webhook.transport_failed",
                summary="Webhook TLS or network transport failed.",
            ) from exc
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError, ssl.SSLError):
                    await writer.wait_closed()


async def resolve_endpoint(
    value: str,
    *,
    resolver: AddressResolver,
    production: bool = True,
    allowed_ports: frozenset[int] = frozenset({443}),
) -> tuple[EndpointTarget, tuple[str, ...]]:
    endpoint = parse_endpoint(
        value,
        production=production,
        allowed_ports=allowed_ports,
    )
    addresses = await resolver.resolve(endpoint.hostname, endpoint.port)
    if production:
        addresses = validate_public_addresses(list(addresses))
    elif not addresses:
        raise MergenConfigurationError("Webhook DNS resolver returned no addresses.")
    return endpoint, addresses


def _request_bytes(
    *,
    endpoint: EndpointTarget,
    body: bytes,
    headers: Mapping[str, str],
) -> bytes:
    protected = {"host", "content-length", "connection", "transfer-encoding"}
    lines = [f"POST {endpoint.request_target} HTTP/1.1", f"Host: {endpoint.authority}"]
    for name, value in sorted(headers.items(), key=lambda item: item[0].lower()):
        normalized = name.lower()
        if (
            normalized in protected
            or not normalized
            or any(character in name for character in "\r\n:")
            or any(character in value for character in "\r\n\x00")
        ):
            raise MergenConfigurationError("Webhook request headers are invalid.")
        lines.append(f"{name}: {value}")
    lines.extend((f"Content-Length: {len(body)}", "Connection: close", "", ""))
    try:
        head = "\r\n".join(lines).encode("ascii")
    except UnicodeEncodeError as exc:
        raise MergenConfigurationError("Webhook request headers must be ASCII.") from exc
    return head + body


def _secure_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


__all__ = [
    "AddressResolver",
    "ConnectionOpener",
    "ExplicitIPTransport",
    "SystemAddressResolver",
    "TransportLimits",
    "TransportResult",
    "resolve_endpoint",
]

"""Conformance adapter for the real PostgreSQL and webhook implementation paths."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import ssl as ssl_module
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_effects import Event, Principal, RetryPolicy, __version__
from fastapi_effects.conformance.contract import Capability, Invariant
from fastapi_effects.conformance.manifest import CapabilityManifest
from fastapi_effects.conformance.protocols import (
    ConformanceAccessDenied,
    WebhookAttemptView,
)
from fastapi_effects.errors import PermanentDeliveryError, RetryableDeliveryError
from fastapi_effects.postgres.leasing import LeaseRepository
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.store import PostgresStore
from fastapi_effects.sqlalchemy.models import SCHEMA, DeliveryRow
from fastapi_effects.sqlalchemy.uow import FastAPIEffectsUnitOfWork
from fastapi_effects.testing.evidence import postgres_evidence_metadata
from fastapi_effects.testing.postgres_driver import PostgresBoundaryDriver
from fastapi_effects.webhooks.address_policy import validate_public_addresses
from fastapi_effects.webhooks.secrets import (
    MasterKey,
    StaticMasterKeyProvider,
    WebhookSecretService,
    decode_public_secret,
)
from fastapi_effects.webhooks.signing import verify_webhook
from fastapi_effects.webhooks.sink import WebhookAttemptResult, WebhookDeliverySink
from fastapi_effects.webhooks.subscriptions import SubscriptionRepository, WebhookRouteProvider
from fastapi_effects.webhooks.transport import ExplicitIPTransport

_CONFORMANCE_TENANT = UUID("b313e510-229d-4ed2-98f3-d910c2a3e420")


class _FixtureResolver:
    def __init__(self) -> None:
        self.addresses: tuple[str, ...] = ()

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        if not hostname or port != 443 or not self.addresses:
            raise AssertionError("Conformance resolver received an unexpected endpoint.")
        return self.addresses


class PostgresWebhookBoundaryDriver(PostgresBoundaryDriver):
    """Exercise the production PostgreSQL, DNS, TLS, HTTP, and signing path."""

    def __init__(
        self,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> None:
        super().__init__(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        self._resolver = _FixtureResolver()
        self._webhook_leases = LeaseRepository()
        self._secret_service = WebhookSecretService(
            StaticMasterKeyProvider(
                keys=(MasterKey("conformance-mk", b"w" * 32),),
                current_key_id="conformance-mk",
            )
        )
        self._sink: WebhookDeliverySink | None = None
        self._server: asyncio.Server | None = None
        self._server_port: int | None = None
        self._tls_files: TemporaryDirectory[str] | None = None
        self._receiver_secret: bytes | None = None
        self._delivery_ids: dict[str, UUID] = {}
        self._receiver_attempts = 0

    @classmethod
    async def create(
        cls,
        *,
        migration_engine: AsyncEngine,
        app_engine: AsyncEngine,
        relay_engine: AsyncEngine,
        roles: RuntimeRoles,
    ) -> PostgresWebhookBoundaryDriver:
        driver = cls(
            migration_engine=migration_engine,
            app_engine=app_engine,
            relay_engine=relay_engine,
            roles=roles,
        )
        await driver._prepare_business_table()
        driver._manifest_metadata = await postgres_evidence_metadata(migration_engine)
        await driver._start_receiver()
        return driver

    @property
    def manifest(self) -> CapabilityManifest:
        core = super().manifest
        metadata = dict(core.metadata)
        metadata.update(
            {
                "webhook.transport": "explicit-ip-tls-http11",
                "webhook.receiver": "local-tls-conformance-fixture",
            }
        )
        return CapabilityManifest(
            adapter_name="fastapi_effects_postgresql-webhooks",
            adapter_version=__version__,
            implementation=("fastapi_effects.testing.webhook_driver.PostgresWebhookBoundaryDriver"),
            capabilities=core.capabilities | {Capability.WEBHOOKS},
            invariants=core.invariants | {Invariant.WEBHOOK_BOUNDARY},
            metadata=metadata,
        )

    async def reset(self) -> None:
        await super().reset()
        async with self._migration_engine.begin() as connection:
            for table in (
                "webhook_audit",
                "webhook_subscription_versions",
                "webhook_subscriptions",
                "webhook_secret_versions",
                "webhook_secret_sets",
            ):
                await connection.execute(text(f"DELETE FROM {SCHEMA}.{table}"))
        self._delivery_ids.clear()
        self._receiver_secret = None
        self._receiver_attempts = 0

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._tls_files is not None:
            self._tls_files.cleanup()
            self._tls_files = None
        await super().close()

    async def public_evidence(self) -> dict[str, int]:
        evidence = await super().public_evidence()
        evidence["webhook_attempts"] = self._receiver_attempts
        return evidence

    async def deliver_webhook(
        self,
        *,
        message_id: str,
        body: bytes,
        endpoint_url: str,
        resolved_addresses: Sequence[str],
        attempt_no: int,
    ) -> WebhookAttemptView:
        try:
            self._resolver.addresses = validate_public_addresses(list(resolved_addresses))
        except PermanentDeliveryError as exc:
            raise ConformanceAccessDenied from exc
        if self._sink is None:
            raise RuntimeError("Webhook conformance receiver is not running.")

        delivery_id = self._delivery_ids.get(message_id)
        if delivery_id is None:
            delivery_id = await self._create_delivery(
                message_id=message_id,
                body=body,
                endpoint_url=endpoint_url,
            )
            self._delivery_ids[message_id] = delivery_id

        async with self._relay_sessions() as session:
            claims = await self._webhook_leases.claim(
                session,
                now=datetime.now(UTC),
                batch_size=1,
                per_tenant=1,
            )
        if len(claims) != 1 or claims[0].delivery.delivery_id != delivery_id:
            raise AssertionError("Webhook conformance delivery was not claimable.")
        claim = claims[0]
        if claim.attempt.attempt_number != attempt_no:
            raise AssertionError("Webhook attempt identity did not advance as expected.")

        result = await self._sink.deliver_attempt(claim)
        now = datetime.now(UTC)
        async with self._relay_sessions() as session:
            if attempt_no == 1:
                await self._webhook_leases.fail(
                    session,
                    claim,
                    RetryableDeliveryError(
                        code="conformance.receiver_succeeded_relay_retry",
                        summary="Injected post-receiver relay retry.",
                    ),
                    now=now,
                )
            else:
                await self._webhook_leases.succeed(session, claim, now=now)
        return _attempt_view(result, attempt_no)

    async def _create_delivery(
        self,
        *,
        message_id: str,
        body: bytes,
        endpoint_url: str,
    ) -> UUID:
        principal = Principal(
            tenant_id=_CONFORMANCE_TENANT,
            subject_id="service:webhook-conformance",
        )
        now = datetime.now(UTC)
        async with (
            self._app_sessions() as session,
            FastAPIEffectsUnitOfWork(
                session=session,
                principal=principal,
                store=PostgresStore(),
                route_providers=(WebhookRouteProvider(),),
            ) as uow,
        ):
            secret = await self._secret_service.create(session, principal=principal, now=now)
            await SubscriptionRepository().create(
                session,
                principal=principal,
                exact_event_types=("conformance.webhook",),
                endpoint_url=endpoint_url,
                retry_policy=RetryPolicy(
                    name="conformance.webhook",
                    max_attempts=3,
                    base_delay_seconds=0,
                    maximum_delay_seconds=0,
                    handler_timeout_seconds=5,
                    lease_duration_seconds=15,
                ),
                secret_set_id=secret.secret_set_id,
                now=now,
            )
            event = await uow.emit(
                Event(
                    type="conformance.webhook",
                    version=1,
                    data={
                        "conformance_message_id": message_id,
                        "source_body_sha256": hashlib.sha256(body).hexdigest(),
                    },
                )
            )
        self._receiver_secret = decode_public_secret(secret.plaintext)
        async with self._relay_sessions() as session:
            delivery_id = await session.scalar(
                select(DeliveryRow.delivery_id).where(
                    DeliveryRow.event_id == event.event_id,
                    DeliveryRow.destination_kind == "webhook",
                )
            )
        if delivery_id is None:
            raise AssertionError("Webhook route provider did not persist a delivery.")
        return delivery_id

    async def _start_receiver(self) -> None:
        tls_files = TemporaryDirectory(prefix="fastapi_effects_webhook-")
        self._tls_files = tls_files
        cert_path, key_path = _write_certificate(Path(tls_files.name))

        server_context = ssl_module.SSLContext(ssl_module.PROTOCOL_TLS_SERVER)
        server_context.minimum_version = ssl_module.TLSVersion.TLSv1_2
        server_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        self._server = await asyncio.start_server(
            self._receive_request,
            host="127.0.0.1",
            port=0,
            ssl=server_context,
        )
        sockets = self._server.sockets or ()
        if not sockets:
            raise RuntimeError("Webhook TLS receiver did not bind a socket.")
        self._server_port = int(sockets[0].getsockname()[1])

        client_context = ssl_module.create_default_context(cafile=cert_path)
        client_context.minimum_version = ssl_module.TLSVersion.TLSv1_2
        self._sink = WebhookDeliverySink(
            sessions=self._relay_sessions,
            secrets=self._secret_service,
            resolver=self._resolver,
            transport=ExplicitIPTransport(
                production=True,
                ssl_context=client_context,
                connection_opener=self._open_fixture_connection,
            ),
            production=True,
        )

    async def _open_fixture_connection(
        self,
        *,
        host: str,
        port: int,
        ssl: ssl_module.SSLContext | None,
        server_hostname: str | None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        ipaddress.ip_address(host)
        if port != 443 or ssl is None or self._server_port is None:
            raise AssertionError("Webhook transport did not preserve production TLS policy.")
        return await asyncio.open_connection(
            host="127.0.0.1",
            port=self._server_port,
            ssl=ssl,
            server_hostname=server_hostname,
        )

    async def _receive_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        status = 400
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
            lines = head[:-4].split(b"\r\n")
            request_line = lines.pop(0)
            if not request_line.startswith(b"POST /hooks HTTP/1.1"):
                raise ValueError("Unexpected webhook request target.")
            headers = _parse_headers(lines)
            length = int(headers.get("content-length", "-1"))
            if not 0 <= length <= 1024 * 1024:
                raise ValueError("Webhook request body length is invalid.")
            body = await asyncio.wait_for(reader.readexactly(length), timeout=5)
            secret = self._receiver_secret
            if secret is None or not verify_webhook(secret=secret, body=body, headers=headers):
                raise ValueError("Webhook receiver rejected the signature.")
            self._receiver_attempts += 1
            status = 202
        except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            status = 400
        response_body = b"receiver-response-must-not-be-persisted"
        writer.write(
            f"HTTP/1.1 {status} {'Accepted' if status == 202 else 'Bad Request'}\r\n"
            f"Content-Length: {len(response_body)}\r\nConnection: close\r\n\r\n".encode()
            + response_body
        )
        await writer.drain()
        writer.close()


def _parse_headers(lines: list[bytes]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in lines:
        name, separator, value = line.partition(b":")
        if not separator:
            raise ValueError("Malformed webhook request header.")
        headers[name.decode("ascii").lower()] = value.strip().decode("latin-1")
    return headers


def _attempt_view(result: WebhookAttemptResult, attempt_no: int) -> WebhookAttemptView:
    return WebhookAttemptView(
        message_id=result.message_id,
        attempt_no=attempt_no,
        request_body_digest=result.request_body_digest,
        signed_body_digest=result.signed_body_digest,
        signature_count=result.signature_count,
        connected_ip=result.connected_ip,
        status_code=result.status_code,
        response_body_persisted=result.response_body_persisted,
    )


def _write_certificate(directory: Path) -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "customer.example")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("customer.example")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "receiver.crt"
    key_path = directory / "receiver.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


__all__ = ["PostgresWebhookBoundaryDriver"]

"""AES-GCM encrypted webhook signing-secret lifecycle."""

from __future__ import annotations

import base64
import binascii
import importlib
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen._optional import require_modules
from fastapi_mergen.core.identity import UUIDSource
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.protocols import UUIDGenerator
from fastapi_mergen.errors import MergenConfigurationError, OptimisticConflict
from fastapi_mergen.webhooks.models import WebhookSecretSetRow, WebhookSecretVersionRow

require_modules(
    feature="Webhook secret encryption",
    extra="webhooks",
    modules=("cryptography",),
)

AESGCM = cast(Any, importlib.import_module("cryptography.hazmat.primitives.ciphers.aead").AESGCM)


@dataclass(frozen=True, slots=True)
class MasterKey:
    key_id: str
    material: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not self.key_id or len(self.key_id) > 128:
            raise MergenConfigurationError("Webhook master key identifier is invalid.")
        if len(self.material) not in {16, 24, 32}:
            raise MergenConfigurationError("Webhook AES master key has an invalid size.")


class MasterKeyProvider(Protocol):
    async def current_key(self) -> MasterKey: ...

    async def key_for(self, key_id: str) -> MasterKey: ...


@dataclass(frozen=True, slots=True)
class StaticMasterKeyProvider:
    """Explicit provider intended for tests and externally loaded process secrets."""

    keys: tuple[MasterKey, ...] = field(repr=False)
    current_key_id: str

    async def current_key(self) -> MasterKey:
        return await self.key_for(self.current_key_id)

    async def key_for(self, key_id: str) -> MasterKey:
        for key in self.keys:
            if key.key_id == key_id:
                return key
        raise MergenConfigurationError("Configured webhook master key is unavailable.")


@dataclass(frozen=True, slots=True)
class CreatedWebhookSecret:
    """One-time return value; plaintext is never recoverable through the public service."""

    secret_set_id: UUID
    version: int
    plaintext: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SigningSecret:
    version: int
    material: bytes = field(repr=False)


class WebhookSecretService:
    def __init__(
        self,
        provider: MasterKeyProvider,
        *,
        uuid_source: UUIDGenerator | None = None,
    ) -> None:
        self._provider = provider
        self._uuid_source = uuid_source or UUIDSource()

    async def create(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        now: datetime,
    ) -> CreatedWebhookSecret:
        _aware(now)
        secret_set_id = self._uuid_source.new_uuid()
        signing_material = secrets.token_bytes(32)
        key = await self._provider.current_key()
        nonce, ciphertext = _encrypt(
            key,
            tenant_id=principal.tenant_id,
            secret_set_id=secret_set_id,
            version=1,
            material=signing_material,
        )
        session.add(
            WebhookSecretSetRow(
                tenant_id=principal.tenant_id,
                secret_set_id=secret_set_id,
                revision=1,
                created_by=principal.subject_id,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            WebhookSecretVersionRow(
                tenant_id=principal.tenant_id,
                secret_set_id=secret_set_id,
                secret_version=1,
                key_id=key.key_id,
                nonce=nonce,
                ciphertext=ciphertext,
                state="active",
                created_at=now,
            )
        )
        await session.flush()
        return CreatedWebhookSecret(
            secret_set_id=secret_set_id,
            version=1,
            plaintext=_encode_public(signing_material),
        )

    async def rotate(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        secret_set_id: UUID,
        expected_revision: int,
        overlap: timedelta,
        now: datetime,
    ) -> CreatedWebhookSecret:
        _aware(now)
        if overlap <= timedelta(0) or overlap > timedelta(days=30):
            raise MergenConfigurationError("Webhook secret overlap must be in (0, 30 days].")
        secret_set = await session.scalar(
            select(WebhookSecretSetRow)
            .where(
                WebhookSecretSetRow.tenant_id == principal.tenant_id,
                WebhookSecretSetRow.secret_set_id == secret_set_id,
            )
            .with_for_update()
        )
        if secret_set is None:
            raise MergenConfigurationError("Webhook secret set does not exist.")
        if secret_set.revision != expected_revision:
            raise OptimisticConflict(resource="webhook_secret_set")
        active = await session.scalar(
            select(WebhookSecretVersionRow)
            .where(
                WebhookSecretVersionRow.tenant_id == principal.tenant_id,
                WebhookSecretVersionRow.secret_set_id == secret_set_id,
                WebhookSecretVersionRow.state == "active",
            )
            .with_for_update()
        )
        if active is None:
            raise MergenConfigurationError("Webhook secret set has no active key.")
        active.state = "retiring"
        active.retiring_until = now + overlap
        version = active.secret_version + 1
        material = secrets.token_bytes(32)
        key = await self._provider.current_key()
        nonce, ciphertext = _encrypt(
            key,
            tenant_id=principal.tenant_id,
            secret_set_id=secret_set_id,
            version=version,
            material=material,
        )
        session.add(
            WebhookSecretVersionRow(
                tenant_id=principal.tenant_id,
                secret_set_id=secret_set_id,
                secret_version=version,
                key_id=key.key_id,
                nonce=nonce,
                ciphertext=ciphertext,
                state="active",
                created_at=now,
            )
        )
        secret_set.revision += 1
        secret_set.updated_at = now
        await session.flush()
        return CreatedWebhookSecret(
            secret_set_id=secret_set_id,
            version=version,
            plaintext=_encode_public(material),
        )

    async def revoke(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        secret_set_id: UUID,
        version: int,
        expected_revision: int,
        now: datetime,
    ) -> None:
        secret_set = await session.scalar(
            select(WebhookSecretSetRow)
            .where(
                WebhookSecretSetRow.tenant_id == principal.tenant_id,
                WebhookSecretSetRow.secret_set_id == secret_set_id,
            )
            .with_for_update()
        )
        if secret_set is None or secret_set.revision != expected_revision:
            raise OptimisticConflict(resource="webhook_secret_set")
        row = await session.scalar(
            select(WebhookSecretVersionRow)
            .where(
                WebhookSecretVersionRow.tenant_id == principal.tenant_id,
                WebhookSecretVersionRow.secret_set_id == secret_set_id,
                WebhookSecretVersionRow.secret_version == version,
            )
            .with_for_update()
        )
        if row is None:
            raise MergenConfigurationError("Webhook secret version does not exist.")
        row.state = "revoked"
        row.retiring_until = None
        row.revoked_at = now
        secret_set.revision += 1
        secret_set.updated_at = now
        await session.flush()

    async def eligible_for_signing(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        secret_set_id: UUID,
        now: datetime,
    ) -> tuple[SigningSecret, ...]:
        """Internal relay operation returning only currently eligible material."""
        rows = (
            await session.scalars(
                select(WebhookSecretVersionRow)
                .where(
                    WebhookSecretVersionRow.tenant_id == tenant_id,
                    WebhookSecretVersionRow.secret_set_id == secret_set_id,
                    (
                        (WebhookSecretVersionRow.state == "active")
                        | (
                            (WebhookSecretVersionRow.state == "retiring")
                            & (WebhookSecretVersionRow.retiring_until >= now)
                        )
                    ),
                )
                .order_by(WebhookSecretVersionRow.secret_version.desc())
            )
        ).all()
        if not rows:
            raise MergenConfigurationError("Webhook delivery has no eligible signing key.")
        result: list[SigningSecret] = []
        for row in rows:
            key = await self._provider.key_for(row.key_id)
            result.append(
                SigningSecret(
                    version=row.secret_version,
                    material=_decrypt(
                        key,
                        tenant_id=tenant_id,
                        secret_set_id=secret_set_id,
                        version=row.secret_version,
                        nonce=bytes(row.nonce),
                        ciphertext=bytes(row.ciphertext),
                    ),
                )
            )
        return tuple(result)


def decode_public_secret(value: str) -> bytes:
    if not isinstance(value, str) or not value.startswith("whsec_"):
        raise MergenConfigurationError("Webhook signing secret is invalid.")
    try:
        decoded = base64.b64decode(value[6:], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise MergenConfigurationError("Webhook signing secret is invalid.") from exc
    if len(decoded) < 16:
        raise MergenConfigurationError("Webhook signing secret is invalid.")
    return decoded


def _encode_public(material: bytes) -> str:
    return "whsec_" + base64.b64encode(material).decode("ascii")


def _associated_data(tenant_id: UUID, secret_set_id: UUID, version: int) -> bytes:
    return (
        b"fastapi-mergen:webhook-secret:v1\x00"
        + tenant_id.bytes
        + secret_set_id.bytes
        + version.to_bytes(8, "big")
    )


def _encrypt(
    key: MasterKey,
    *,
    tenant_id: UUID,
    secret_set_id: UUID,
    version: int,
    material: bytes,
) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key.material).encrypt(
        nonce,
        material,
        _associated_data(tenant_id, secret_set_id, version),
    )
    return nonce, ciphertext


def _decrypt(
    key: MasterKey,
    *,
    tenant_id: UUID,
    secret_set_id: UUID,
    version: int,
    nonce: bytes,
    ciphertext: bytes,
) -> bytes:
    try:
        return cast(
            bytes,
            AESGCM(key.material).decrypt(
                nonce,
                ciphertext,
                _associated_data(tenant_id, secret_set_id, version),
            ),
        )
    except Exception as exc:
        raise MergenConfigurationError("Webhook encrypted secret could not be opened.") from exc


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MergenConfigurationError("Webhook secret time must be timezone-aware.")


__all__ = [
    "CreatedWebhookSecret",
    "MasterKey",
    "MasterKeyProvider",
    "SigningSecret",
    "StaticMasterKeyProvider",
    "WebhookSecretService",
    "decode_public_secret",
]

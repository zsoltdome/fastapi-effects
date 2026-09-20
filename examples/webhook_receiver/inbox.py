"""Example-owned PostgreSQL inbox for transactional receiver deduplication."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import Column, DateTime, LargeBinary, MetaData, String, Table, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fastapi_effects.errors import FastAPIEffectsConfigurationError

_SAFE_NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_MESSAGE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

metadata = MetaData()
webhook_inbox = Table(
    "example_webhook_inbox",
    metadata,
    Column("source_namespace", String(128), primary_key=True),
    Column("message_id", String(128), primary_key=True),
    Column("body_sha256", LargeBinary(32), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class InboxConflictError(Exception):
    """A verified message identity was previously committed with other bytes."""


@dataclass(frozen=True, slots=True)
class InboxResult:
    duplicate: bool
    body_sha256: str


async def install_inbox_schema(engine: AsyncEngine) -> None:
    """Install the example-owned table; applications should use their migrations."""

    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)


async def apply_once(
    session: AsyncSession,
    *,
    source_namespace: str,
    message_id: str,
    body: bytes,
    effect: Callable[[AsyncSession], Awaitable[None]],
) -> InboxResult:
    """Record a verified message and its local effect in the caller's transaction."""

    if not session.in_transaction():
        raise FastAPIEffectsConfigurationError("Webhook inbox requires an explicit transaction.")
    if not isinstance(source_namespace, str) or _SAFE_NAMESPACE.fullmatch(source_namespace) is None:
        raise FastAPIEffectsConfigurationError("Webhook inbox source namespace is invalid.")
    if not isinstance(message_id, str) or _MESSAGE_ID.fullmatch(message_id) is None:
        raise FastAPIEffectsConfigurationError("Webhook inbox message ID is invalid.")
    if not isinstance(body, bytes):
        raise FastAPIEffectsConfigurationError("Webhook inbox body must be bytes.")
    digest = hashlib.sha256(body).digest()
    inserted = await session.scalar(
        insert(webhook_inbox)
        .values(
            source_namespace=source_namespace,
            message_id=message_id,
            body_sha256=digest,
        )
        .on_conflict_do_nothing(
            index_elements=(webhook_inbox.c.source_namespace, webhook_inbox.c.message_id)
        )
        .returning(webhook_inbox.c.message_id)
    )
    if inserted is not None:
        await effect(session)
        return InboxResult(duplicate=False, body_sha256=digest.hex())

    committed_digest = await session.scalar(
        select(webhook_inbox.c.body_sha256).where(
            webhook_inbox.c.source_namespace == source_namespace,
            webhook_inbox.c.message_id == message_id,
        )
    )
    if not isinstance(committed_digest, bytes) or committed_digest != digest:
        raise InboxConflictError("Webhook message identity conflicts with a prior body.")
    return InboxResult(duplicate=True, body_sha256=digest.hex())


__all__ = [
    "InboxConflictError",
    "InboxResult",
    "apply_once",
    "install_inbox_schema",
    "metadata",
    "webhook_inbox",
]

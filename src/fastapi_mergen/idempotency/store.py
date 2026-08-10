"""Advisory-lock serialized command-ledger persistence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_mergen.core.identity import UUIDSource
from fastapi_mergen.core.principal import Principal
from fastapi_mergen.core.protocols import UUIDGenerator
from fastapi_mergen.errors import CommandConflict, CommandInProgress, MergenConfigurationError
from fastapi_mergen.idempotency.fingerprint import RequestFingerprint
from fastapi_mergen.idempotency.models import CommandIdentity, CommandRow, CommandState
from fastapi_mergen.idempotency.responses import CapturedResponse
from fastapi_mergen.observability.events import RuntimeEvent, RuntimeEventKind, TraceLineage
from fastapi_mergen.observability.protocols import EventSink, NoOpEventSink, record_safely


@dataclass(frozen=True, slots=True)
class CommandAcquisition:
    command_id: UUID
    generation: int
    replayed: bool
    response: CapturedResponse | None = None

    def __post_init__(self) -> None:
        if self.replayed != (self.response is not None):
            raise MergenConfigurationError("Command acquisition response state is invalid.")


class CommandStore:
    """Store commands inside a caller-owned application transaction."""

    def __init__(
        self,
        *,
        uuid_source: UUIDGenerator | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self._uuid_source = uuid_source or UUIDSource()
        self._event_sink = event_sink or NoOpEventSink()

    async def acquire(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        identity: CommandIdentity,
        fingerprint: RequestFingerprint,
        now: datetime,
        ttl: timedelta,
    ) -> CommandAcquisition:
        _require_transaction(session)
        _validate_request(principal, identity, now, ttl)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:command_lock)"),
            {"command_lock": _advisory_key(identity)},
        )
        row = await session.scalar(
            select(CommandRow)
            .where(
                CommandRow.tenant_id == identity.tenant_id,
                CommandRow.route_id == identity.route_id,
                CommandRow.method == identity.method,
                CommandRow.key_digest == identity.key_digest,
                CommandRow.is_current.is_(True),
            )
            .with_for_update()
        )
        generation = 1
        if row is not None and row.expires_at <= now:
            generation = row.generation + 1
            row.state = CommandState.SUPERSEDED.value
            row.is_current = False
            row.superseded_at = now
            row.updated_at = now
            await session.flush()
            row = None
        if row is None:
            command_id = self._uuid_source.new_uuid()
            session.add(
                CommandRow(
                    tenant_id=identity.tenant_id,
                    command_id=command_id,
                    route_id=identity.route_id,
                    method=identity.method,
                    key_digest=identity.key_digest,
                    generation=generation,
                    is_current=True,
                    subject_id=principal.subject_id,
                    fingerprint_version=fingerprint.version,
                    fingerprint=fingerprint.digest,
                    state=CommandState.IN_PROGRESS.value,
                    response_status=None,
                    response_headers=None,
                    response_body=None,
                    response_media_type=None,
                    created_at=now,
                    updated_at=now,
                    expires_at=now + ttl,
                    completed_at=None,
                    superseded_at=None,
                )
            )
            await session.flush()
            self._record(RuntimeEventKind.COMMAND_STARTED, now, command_id)
            return CommandAcquisition(
                command_id=command_id,
                generation=generation,
                replayed=False,
            )
        if (
            row.subject_id != principal.subject_id
            or row.fingerprint_version != fingerprint.version
            or row.fingerprint != fingerprint.digest
        ):
            self._record(RuntimeEventKind.COMMAND_CONFLICT, now, row.command_id)
            raise CommandConflict
        if row.state == CommandState.COMPLETED.value:
            self._record(RuntimeEventKind.COMMAND_REPLAYED, now, row.command_id)
            return CommandAcquisition(
                command_id=row.command_id,
                generation=row.generation,
                replayed=True,
                response=_response_from_row(row),
            )
        self._record(RuntimeEventKind.COMMAND_CONFLICT, now, row.command_id)
        raise CommandInProgress

    async def complete(
        self,
        session: AsyncSession,
        *,
        acquisition: CommandAcquisition,
        tenant_id: UUID,
        response: CapturedResponse,
        now: datetime,
    ) -> None:
        _require_transaction(session)
        if acquisition.replayed:
            raise MergenConfigurationError("A replayed command cannot be completed again.")
        row = await session.scalar(
            select(CommandRow)
            .where(
                CommandRow.tenant_id == tenant_id,
                CommandRow.command_id == acquisition.command_id,
                CommandRow.generation == acquisition.generation,
            )
            .with_for_update()
        )
        if row is None or row.state != CommandState.IN_PROGRESS.value or not row.is_current:
            raise CommandInProgress
        row.state = CommandState.COMPLETED.value
        row.response_status = response.status_code
        row.response_headers = dict(response.headers)
        row.response_body = response.body
        row.response_media_type = response.media_type
        row.completed_at = now
        row.updated_at = now
        await session.flush()
        self._record(RuntimeEventKind.COMMAND_COMPLETED, now, acquisition.command_id)

    async def prune(
        self,
        session: AsyncSession,
        *,
        before: datetime,
        batch_size: int = 100,
    ) -> int:
        """Delete expired terminal history in one bounded maintenance transaction."""
        if session.in_transaction():
            raise MergenConfigurationError("Command pruning requires an idle session.")
        if before.tzinfo is None or before.utcoffset() is None:
            raise MergenConfigurationError("Command pruning cutoff must be timezone-aware.")
        if not 1 <= batch_size <= 10_000:
            raise MergenConfigurationError("Command pruning batch size is invalid.")
        async with session.begin():
            deleted = await session.scalar(
                text("SELECT fastapi_mergen.prune_commands(:cutoff, :batch_size)"),
                {"cutoff": before, "batch_size": batch_size},
            )
        if not isinstance(deleted, int):
            raise MergenConfigurationError("Command pruning returned an invalid result.")
        if deleted:
            record_safely(
                self._event_sink,
                RuntimeEvent(
                    RuntimeEventKind.COMMAND_PRUNED,
                    before,
                    {"pruned.count": deleted},
                ),
            )
        return deleted

    def _record(self, kind: RuntimeEventKind, now: datetime, command_id: UUID) -> None:
        record_safely(
            self._event_sink,
            RuntimeEvent(
                kind,
                now,
                {"capability": "commands"},
                TraceLineage(command_id=command_id),
            ),
        )


def _validate_request(
    principal: Principal,
    identity: CommandIdentity,
    now: datetime,
    ttl: timedelta,
) -> None:
    if principal.tenant_id != identity.tenant_id:
        raise MergenConfigurationError("Command identity tenant does not match its principal.")
    if now.tzinfo is None or now.utcoffset() is None:
        raise MergenConfigurationError("Command timestamp must be timezone-aware.")
    if ttl < timedelta(seconds=1) or ttl > timedelta(days=365):
        raise MergenConfigurationError("Command expiry interval is invalid.")


def _require_transaction(session: AsyncSession) -> None:
    if not session.in_transaction():
        raise MergenConfigurationError("Command storage requires an active transaction.")


def _advisory_key(identity: CommandIdentity) -> int:
    digest = hashlib.sha256(
        b"fastapi-mergen:command-lock:v1\0"
        + identity.tenant_id.bytes
        + identity.route_id.encode("ascii")
        + b"\0"
        + identity.method.encode("ascii")
        + b"\0"
        + identity.key_digest
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _response_from_row(row: CommandRow) -> CapturedResponse:
    if (
        row.response_status is None
        or row.response_headers is None
        or row.response_body is None
        or row.response_media_type is None
    ):
        raise MergenConfigurationError("Completed command response is unavailable.")
    return CapturedResponse(
        status_code=row.response_status,
        headers=row.response_headers,
        body=row.response_body,
        media_type=row.response_media_type,
    )


__all__ = ["CommandAcquisition", "CommandStore"]

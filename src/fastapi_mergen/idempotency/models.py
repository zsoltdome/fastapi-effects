"""Command identity domain values and SQLAlchemy ledger mapping."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from fastapi_mergen.errors import MergenConfigurationError
from fastapi_mergen.sqlalchemy.models import JSON_VALUE, SCHEMA, Base

_ROUTE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_METHOD = re.compile(r"^[A-Z]{3,16}$")


class CommandState(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class CommandIdentity:
    tenant_id: UUID
    route_id: str
    method: str
    key_digest: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise MergenConfigurationError("Command tenant identity is invalid.")
        if not isinstance(self.route_id, str) or not _ROUTE.fullmatch(self.route_id):
            raise MergenConfigurationError("Command route identity is invalid.")
        if not isinstance(self.method, str) or not _METHOD.fullmatch(self.method):
            raise MergenConfigurationError("Command method is invalid.")
        if not isinstance(self.key_digest, bytes) or len(self.key_digest) != 32:
            raise MergenConfigurationError("Command key digest is invalid.")

    @classmethod
    def from_key(
        cls,
        *,
        tenant_id: UUID,
        route_id: str,
        method: str,
        key: str | bytes,
    ) -> CommandIdentity:
        if isinstance(key, str):
            try:
                raw = key.encode("utf-8")
            except UnicodeError as exc:
                raise MergenConfigurationError("Idempotency key is invalid UTF-8.") from exc
        elif isinstance(key, bytes):
            raw = key
        else:
            raise MergenConfigurationError("Idempotency key must be text or bytes.")
        if not 1 <= len(raw) <= 512 or any(item < 0x20 or item == 0x7F for item in raw):
            raise MergenConfigurationError("Idempotency key is invalid or oversized.")
        return cls(
            tenant_id=tenant_id,
            route_id=route_id,
            method=method.upper(),
            key_digest=hashlib.sha256(raw).digest(),
        )


class CommandRow(Base):
    __tablename__ = "commands"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "route_id",
            "method",
            "key_digest",
            "generation",
        ),
        CheckConstraint("octet_length(key_digest) = 32", name="command_key_digest_size"),
        CheckConstraint("octet_length(fingerprint) = 32", name="command_fingerprint_size"),
        CheckConstraint("generation > 0", name="command_generation_positive"),
        CheckConstraint("fingerprint_version > 0", name="command_fingerprint_version_positive"),
        CheckConstraint("expires_at > created_at", name="command_expiry_after_creation"),
        CheckConstraint("updated_at >= created_at", name="command_update_after_creation"),
        CheckConstraint(
            "response_status IS NULL OR response_status BETWEEN 200 AND 599",
            name="command_response_status",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="command_completion_after_creation",
        ),
        CheckConstraint(
            "superseded_at IS NULL OR superseded_at >= created_at",
            name="command_supersession_after_creation",
        ),
        CheckConstraint(
            "response_body IS NULL OR octet_length(response_body) <= 262144",
            name="command_response_body_bounded",
        ),
        CheckConstraint(
            "response_headers IS NULL OR jsonb_typeof(response_headers) = 'object'",
            name="command_response_headers_object",
        ),
        CheckConstraint(
            "response_media_type IS NULL OR response_media_type IN "
            "('application/json','application/problem+json','text/plain')",
            name="command_response_media_type",
        ),
        CheckConstraint(
            "state IN ('in_progress','completed','superseded')",
            name="command_state",
        ),
        CheckConstraint(
            "(state = 'superseded') = (is_current = false AND superseded_at IS NOT NULL)",
            name="command_supersession_coherent",
        ),
        CheckConstraint(
            "(state = 'completed' AND completed_at IS NOT NULL AND "
            "response_status IS NOT NULL AND response_headers IS NOT NULL AND "
            "response_body IS NOT NULL AND response_media_type IS NOT NULL) OR "
            "(state = 'in_progress' AND completed_at IS NULL AND response_status IS NULL AND "
            "response_headers IS NULL AND response_body IS NULL AND "
            "response_media_type IS NULL) OR state = 'superseded'",
            name="command_response_coherent",
        ),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    command_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    route_id: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    key_digest: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subject_id: Mapped[str] = mapped_column(String(512), nullable=False)
    fingerprint_version: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict[str, str] | None] = mapped_column(JSON_VALUE, nullable=True)
    response_body: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    response_media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index(
    "uq_commands_current_identity",
    CommandRow.tenant_id,
    CommandRow.route_id,
    CommandRow.method,
    CommandRow.key_digest,
    unique=True,
    postgresql_where=CommandRow.is_current == true(),
)
Index("ix_commands_retention", CommandRow.state, CommandRow.updated_at)

COMMAND_TABLES = cast(tuple[Table, ...], (CommandRow.__table__,))

__all__ = [
    "COMMAND_TABLES",
    "CommandIdentity",
    "CommandRow",
    "CommandState",
]

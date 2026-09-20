"""Private SQLAlchemy mappings for the authoritative PostgreSQL schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

SCHEMA = "fastapi_effects"
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
JSON_VALUE = JSON().with_variant(JSONB(none_as_null=True), "postgresql")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class SchemaRevisionRow(Base):
    __tablename__ = "schema_revision"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
        {"schema": SCHEMA},
    )

    component: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id"),
        CheckConstraint("event_version > 0", name="event_version_positive"),
        CheckConstraint("canonical_version > 0", name="canonical_version_positive"),
        CheckConstraint("octet_length(payload_sha256) = 32", name="payload_sha256_size"),
        CheckConstraint(
            "(dedupe_namespace IS NULL) = (dedupe_key IS NULL)",
            name="dedupe_fields_paired",
        ),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[Any] = mapped_column(JSON_VALUE, nullable=False)
    payload_canonical: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    principal: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    causation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    traceparent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    tracestate: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dedupe_namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


Index(
    "uq_events_tenant_dedupe",
    EventRow.tenant_id,
    EventRow.dedupe_namespace,
    EventRow.dedupe_key,
    unique=True,
    postgresql_where=EventRow.dedupe_namespace.is_not(None),
)
Index("ix_events_tenant_created", EventRow.tenant_id, EventRow.created_at)


class DeliveryRow(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "event_id"],
            [f"{SCHEMA}.events.tenant_id", f"{SCHEMA}.events.event_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "replay_of"],
            [f"{SCHEMA}.deliveries.tenant_id", f"{SCHEMA}.deliveries.delivery_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "delivery_id"),
        CheckConstraint("route_version > 0", name="route_version_positive"),
        CheckConstraint("attempts_started >= 0", name="attempts_started_nonnegative"),
        CheckConstraint(
            "state IN ('pending','leased','retry_wait','succeeded','dead')",
            name="delivery_state",
        ),
        CheckConstraint(
            "(state = 'leased') = (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="delivery_lease_coherent",
        ),
        CheckConstraint(
            "(replay_of IS NULL AND replay_actor IS NULL AND replay_reason IS NULL) OR "
            "(replay_of IS NOT NULL AND replay_actor IS NOT NULL AND replay_reason IS NOT NULL)",
            name="delivery_replay_audit_coherent",
        ),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    delivery_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    event_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    route_key: Mapped[str] = mapped_column(String(128), nullable=False)
    route_version: Mapped[int] = mapped_column(Integer, nullable=False)
    destination_kind: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_key: Mapped[str] = mapped_column(String(128), nullable=False)
    route_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    route_snapshot_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts_started: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replay_of: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    replay_actor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    replay_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index(
    "uq_deliveries_original_route",
    DeliveryRow.tenant_id,
    DeliveryRow.event_id,
    DeliveryRow.route_key,
    DeliveryRow.route_version,
    DeliveryRow.destination_kind,
    DeliveryRow.destination_key,
    unique=True,
    postgresql_where=DeliveryRow.replay_of.is_(None),
)
Index(
    "ix_deliveries_claim",
    DeliveryRow.state,
    DeliveryRow.next_attempt_at,
    DeliveryRow.tenant_id,
    DeliveryRow.created_at,
)


class AttemptRow(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "delivery_id"],
            [f"{SCHEMA}.deliveries.tenant_id", f"{SCHEMA}.deliveries.delivery_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "delivery_id", "attempt_number"),
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        CheckConstraint(
            "outcome IN ('started','succeeded','retryable','terminal','abandoned','lease_lost')",
            name="attempt_outcome",
        ),
        CheckConstraint(
            "(outcome = 'started' AND finished_at IS NULL) OR "
            "(outcome <> 'started' AND finished_at IS NOT NULL)",
            name="attempt_finish_coherent",
        ),
        CheckConstraint(
            "(outcome IN ('started','succeeded') AND failure_code IS NULL AND "
            "failure_summary IS NULL) OR (outcome NOT IN ('started','succeeded') AND "
            "failure_code IS NOT NULL AND failure_summary IS NOT NULL)",
            name="attempt_failure_coherent",
        ),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    attempt_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    delivery_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_token: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_attempts_delivery", AttemptRow.tenant_id, AttemptRow.delivery_id, AttemptRow.started_at)

CORE_TABLES = cast(
    tuple[Table, ...],
    (
        SchemaRevisionRow.__table__,
        EventRow.__table__,
        DeliveryRow.__table__,
        AttemptRow.__table__,
    ),
)


def schema_ddl() -> tuple[str, ...]:
    """Small explicit objects not expressible through portable metadata."""
    return (
        f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}",
        (
            f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
            "VALUES ('core', 1, CURRENT_TIMESTAMP) "
            "ON CONFLICT (component) DO UPDATE SET revision = EXCLUDED.revision"
        ),
    )


__all__ = [
    "CORE_TABLES",
    "NAMING_CONVENTION",
    "SCHEMA",
    "AttemptRow",
    "Base",
    "DeliveryRow",
    "EventRow",
    "SchemaRevisionRow",
]

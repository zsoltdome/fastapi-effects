"""Durable Taskiq handoff SQLAlchemy mapping."""

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
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from fastapi_effects.sqlalchemy.models import JSON_VALUE, SCHEMA, Base


class TaskiqHandoffRow(Base):
    __tablename__ = "taskiq_handoffs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "delivery_id"],
            [f"{SCHEMA}.deliveries.tenant_id", f"{SCHEMA}.deliveries.delivery_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id"],
            [f"{SCHEMA}.attempts.tenant_id", f"{SCHEMA}.attempts.attempt_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "delivery_id", "attempt_id"),
        UniqueConstraint("task_id"),
        CheckConstraint(
            "state IN ('prepared','enqueued','executing','succeeded','retry_wait','dead')",
            name="taskiq_handoff_state",
        ),
        CheckConstraint("execution_count >= 0", name="taskiq_execution_count_nonnegative"),
        CheckConstraint(
            "(state = 'executing') = "
            "(execution_token IS NOT NULL AND execution_deadline IS NOT NULL)",
            name="taskiq_execution_coherent",
        ),
        CheckConstraint(
            "(state = 'prepared' AND enqueued_at IS NULL) OR "
            "(state IN ('enqueued','executing','succeeded') AND enqueued_at IS NOT NULL) OR "
            "state IN ('retry_wait','dead')",
            name="taskiq_enqueue_coherent",
        ),
        CheckConstraint(
            "(state IN ('succeeded','retry_wait','dead') AND finished_at IS NOT NULL) OR "
            "(state NOT IN ('succeeded','retry_wait','dead') AND finished_at IS NULL)",
            name="taskiq_finish_coherent",
        ),
        CheckConstraint(
            "(state IN ('retry_wait','dead') AND failure_code IS NOT NULL AND "
            "failure_summary IS NOT NULL) OR "
            "(state NOT IN ('retry_wait','dead') AND failure_code IS NULL AND "
            "failure_summary IS NULL)",
            name="taskiq_failure_coherent",
        ),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    handoff_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    delivery_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    handoff_token: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    principal: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    route_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    route_snapshot_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    execution_token: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    execution_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


Index(
    "ix_taskiq_handoffs_recovery",
    TaskiqHandoffRow.state,
    TaskiqHandoffRow.execution_deadline,
    TaskiqHandoffRow.updated_at,
)

TASKIQ_TABLES = cast(tuple[Table, ...], (TaskiqHandoffRow.__table__,))

__all__ = ["TASKIQ_TABLES", "TaskiqHandoffRow"]

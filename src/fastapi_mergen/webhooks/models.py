"""SQLAlchemy mappings for versioned subscriptions and encrypted secrets."""

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

from fastapi_mergen.sqlalchemy.models import JSON_VALUE, SCHEMA, Base


class WebhookSubscriptionRow(Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "subscription_id"),
        CheckConstraint("current_version > 0", name="webhook_subscription_version_positive"),
        CheckConstraint("revision > 0", name="webhook_subscription_revision_positive"),
        CheckConstraint(
            "state IN ('active','paused','disabled')",
            name="webhook_subscription_state",
        ),
        CheckConstraint("failure_streak >= 0", name="webhook_failure_streak_nonnegative"),
        CheckConstraint("auto_pause_threshold > 0", name="webhook_pause_threshold_positive"),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    failure_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auto_pause_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    created_by: Mapped[str] = mapped_column(String(512), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index(
    "ix_webhook_subscriptions_tenant_state",
    WebhookSubscriptionRow.tenant_id,
    WebhookSubscriptionRow.state,
)


class WebhookSecretSetRow(Base):
    __tablename__ = "webhook_secret_sets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "secret_set_id"),
        CheckConstraint("revision > 0", name="webhook_secret_set_revision_positive"),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    secret_set_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WebhookSecretVersionRow(Base):
    __tablename__ = "webhook_secret_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "secret_set_id"],
            [
                f"{SCHEMA}.webhook_secret_sets.tenant_id",
                f"{SCHEMA}.webhook_secret_sets.secret_set_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint("secret_version > 0", name="webhook_secret_version_positive"),
        CheckConstraint(
            "state IN ('active','retiring','revoked')",
            name="webhook_secret_state",
        ),
        CheckConstraint("octet_length(nonce) = 12", name="webhook_secret_nonce_size"),
        CheckConstraint("octet_length(ciphertext) >= 16", name="webhook_secret_ciphertext_size"),
        CheckConstraint(
            "(state = 'retiring' AND retiring_until IS NOT NULL) OR "
            "(state <> 'retiring' AND retiring_until IS NULL)",
            name="webhook_secret_retirement_coherent",
        ),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    secret_set_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    secret_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    retiring_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index(
    "ix_webhook_secret_versions_eligible",
    WebhookSecretVersionRow.tenant_id,
    WebhookSecretVersionRow.secret_set_id,
    WebhookSecretVersionRow.state,
)


class WebhookSubscriptionVersionRow(Base):
    __tablename__ = "webhook_subscription_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            [
                f"{SCHEMA}.webhook_subscriptions.tenant_id",
                f"{SCHEMA}.webhook_subscriptions.subscription_id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "secret_set_id"],
            [
                f"{SCHEMA}.webhook_secret_sets.tenant_id",
                f"{SCHEMA}.webhook_secret_sets.secret_set_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="webhook_subscription_history_version_positive"),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    exact_event_types: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    retry_policy: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    secret_set_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index(
    "ix_webhook_subscription_versions_events",
    WebhookSubscriptionVersionRow.exact_event_types,
    postgresql_using="gin",
)


class WebhookAuditRow(Base):
    __tablename__ = "webhook_audit"
    __table_args__ = ({"schema": SCHEMA},)

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    audit_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(512), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index(
    "ix_webhook_audit_tenant_occurred",
    WebhookAuditRow.tenant_id,
    WebhookAuditRow.occurred_at,
)


WEBHOOK_TABLES = cast(
    tuple[Table, ...],
    (
        WebhookSecretSetRow.__table__,
        WebhookSubscriptionRow.__table__,
        WebhookSecretVersionRow.__table__,
        WebhookSubscriptionVersionRow.__table__,
        WebhookAuditRow.__table__,
    ),
)

__all__ = [
    "WEBHOOK_TABLES",
    "WebhookAuditRow",
    "WebhookSecretSetRow",
    "WebhookSecretVersionRow",
    "WebhookSubscriptionRow",
    "WebhookSubscriptionVersionRow",
]

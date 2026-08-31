"""Install bounded tenant-bound webhook retention.

Revision ID: 0005_webhook_retention
Revises: 0004_commands
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.postgres.migrations.frozen_v1 import (
    SCHEMA_V1,
    role_names_v1,
    webhook_retention_sql_v1,
)

revision = "0005_webhook_retention"
down_revision = "0004_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    config = op.get_context().config
    if config is None:
        raise RuntimeError("Alembic migration configuration is unavailable.")
    configured = role_names_v1(config)
    for statement in webhook_retention_sql_v1(configured):
        op.execute(statement)
    op.execute(
        f"UPDATE {SCHEMA_V1}.schema_revision SET revision = 2, "
        "installed_at = CURRENT_TIMESTAMP WHERE component = 'webhooks'"
    )


def downgrade() -> None:
    op.execute(
        f"DROP FUNCTION IF EXISTS {SCHEMA_V1}.prune_webhook_history"
        "(uuid, timestamp with time zone, integer)"
    )
    op.execute(
        f"UPDATE {SCHEMA_V1}.schema_revision SET revision = 1, "
        "installed_at = CURRENT_TIMESTAMP WHERE component = 'webhooks'"
    )

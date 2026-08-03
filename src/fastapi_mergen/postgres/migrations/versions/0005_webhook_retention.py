"""Install bounded tenant-bound webhook retention.

Revision ID: 0005_webhook_retention
Revises: 0004_commands
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.webhook_schema import webhook_retention_sql
from fastapi_mergen.sqlalchemy.models import SCHEMA

revision = "0005_webhook_retention"
down_revision = "0004_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    config = op.get_context().config
    if config is None:
        raise RuntimeError("Alembic migration configuration is unavailable.")
    configured = config.attributes.get("runtime_roles", RuntimeRoles())
    if not isinstance(configured, RuntimeRoles):
        raise TypeError("runtime_roles must be a RuntimeRoles value.")
    for statement in webhook_retention_sql(configured):
        op.execute(statement)
    op.execute(
        f"UPDATE {SCHEMA}.schema_revision SET revision = 2, "
        "installed_at = CURRENT_TIMESTAMP WHERE component = 'webhooks'"
    )


def downgrade() -> None:
    op.execute(
        f"DROP FUNCTION IF EXISTS {SCHEMA}.prune_webhook_history"
        "(uuid, timestamp with time zone, integer)"
    )
    op.execute(
        f"UPDATE {SCHEMA}.schema_revision SET revision = 1, "
        "installed_at = CURRENT_TIMESTAMP WHERE component = 'webhooks'"
    )

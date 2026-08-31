"""Install versioned webhook subscriptions and encrypted secrets.

Revision ID: 0002_webhooks
Revises: 0001_core_runtime
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.postgres.migrations.frozen_v1 import (
    SCHEMA_V1,
    WEBHOOK_DDL_V1,
    WEBHOOK_TABLE_NAMES_V1,
    role_names_v1,
    webhook_grant_sql_v1,
    webhook_rls_sql_v1,
)
from fastapi_mergen.postgres.migrations.safety import reject_nonempty_downgrade

revision = "0002_webhooks"
down_revision = "0001_core_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    config = op.get_context().config
    if config is None:
        raise RuntimeError("Alembic migration configuration is unavailable.")
    configured = role_names_v1(config)
    for statement in WEBHOOK_DDL_V1:
        op.execute(statement)
    for table in WEBHOOK_TABLE_NAMES_V1:
        op.execute(f"ALTER TABLE {SCHEMA_V1}.{table} OWNER TO {configured.migration}")
    op.execute(
        f"INSERT INTO {SCHEMA_V1}.schema_revision(component, revision, installed_at) "
        "VALUES ('webhooks', 1, CURRENT_TIMESTAMP) ON CONFLICT (component) "
        "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
    )
    for statement in (*webhook_rls_sql_v1(configured), *webhook_grant_sql_v1(configured)):
        op.execute(statement)


def downgrade() -> None:
    connection = op.get_bind()
    reject_nonempty_downgrade(connection, WEBHOOK_TABLE_NAMES_V1)
    op.execute(f"DELETE FROM {SCHEMA_V1}.schema_revision WHERE component = 'webhooks'")
    for table in reversed(WEBHOOK_TABLE_NAMES_V1):
        op.execute(f"DROP TABLE IF EXISTS {SCHEMA_V1}.{table}")

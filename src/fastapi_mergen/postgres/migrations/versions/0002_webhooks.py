"""Install versioned webhook subscriptions and encrypted secrets.

Revision ID: 0002_webhooks
Revises: 0001_core_runtime
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.postgres.migrations.safety import reject_nonempty_downgrade
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.webhook_schema import webhook_grant_sql, webhook_rls_sql
from fastapi_mergen.sqlalchemy.models import SCHEMA
from fastapi_mergen.webhooks.models import WEBHOOK_TABLES

revision = "0002_webhooks"
down_revision = "0001_core_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    config = op.get_context().config
    if config is None:
        raise RuntimeError("Alembic migration configuration is unavailable.")
    configured = config.attributes.get("runtime_roles", RuntimeRoles())
    if not isinstance(configured, RuntimeRoles):
        raise TypeError("runtime_roles must be a RuntimeRoles value.")
    for table in WEBHOOK_TABLES:
        table.create(connection, checkfirst=True)
        op.execute(f"ALTER TABLE {SCHEMA}.{table.name} OWNER TO {configured.migration}")
    op.execute(
        f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
        "VALUES ('webhooks', 1, CURRENT_TIMESTAMP) ON CONFLICT (component) "
        "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
    )
    for statement in (*webhook_rls_sql(configured), *webhook_grant_sql(configured)):
        op.execute(statement)


def downgrade() -> None:
    connection = op.get_bind()
    reject_nonempty_downgrade(connection, tuple(table.name for table in WEBHOOK_TABLES))
    op.execute(f"DELETE FROM {SCHEMA}.schema_revision WHERE component = 'webhooks'")
    for table in reversed(WEBHOOK_TABLES):
        table.drop(connection, checkfirst=True)

"""Install the durable Taskiq handoff boundary.

Revision ID: 0003_taskiq
Revises: 0002_webhooks
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.executors.taskiq.models import TASKIQ_TABLES
from fastapi_mergen.postgres.executor_schema import executor_schema_sql
from fastapi_mergen.postgres.migrations.safety import reject_nonempty_downgrade
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.sqlalchemy.models import SCHEMA

revision = "0003_taskiq"
down_revision = "0002_webhooks"
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
    for table in TASKIQ_TABLES:
        table.create(connection, checkfirst=True)
        op.execute(f"ALTER TABLE {SCHEMA}.{table.name} OWNER TO {configured.migration}")
    op.execute(
        f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
        "VALUES ('executor.taskiq', 1, CURRENT_TIMESTAMP) ON CONFLICT (component) "
        "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
    )
    for statement in executor_schema_sql(configured):
        op.execute(statement)


def downgrade() -> None:
    connection = op.get_bind()
    reject_nonempty_downgrade(connection, tuple(table.name for table in TASKIQ_TABLES))
    op.execute(f"DELETE FROM {SCHEMA}.schema_revision WHERE component = 'executor.taskiq'")
    for table in reversed(TASKIQ_TABLES):
        table.drop(connection, checkfirst=True)

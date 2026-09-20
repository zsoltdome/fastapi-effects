"""Install the durable Taskiq handoff boundary.

Revision ID: 0003_taskiq
Revises: 0002_webhooks
"""

from __future__ import annotations

from alembic import op

from fastapi_effects.postgres.migrations.frozen_v1 import (
    SCHEMA_V1,
    TASKIQ_DDL_V1,
    TASKIQ_TABLE_NAMES_V1,
    executor_schema_sql_v1,
    role_names_v1,
)
from fastapi_effects.postgres.migrations.safety import reject_nonempty_downgrade

revision = "0003_taskiq"
down_revision = "0002_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    config = op.get_context().config
    if config is None:
        raise RuntimeError("Alembic migration configuration is unavailable.")
    configured = role_names_v1(config)
    for statement in TASKIQ_DDL_V1:
        op.execute(statement)
    for table in TASKIQ_TABLE_NAMES_V1:
        op.execute(f"ALTER TABLE {SCHEMA_V1}.{table} OWNER TO {configured.migration}")
    op.execute(
        f"INSERT INTO {SCHEMA_V1}.schema_revision(component, revision, installed_at) "
        "VALUES ('executor.taskiq', 1, CURRENT_TIMESTAMP) ON CONFLICT (component) "
        "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
    )
    for statement in executor_schema_sql_v1(configured):
        op.execute(statement)


def downgrade() -> None:
    connection = op.get_bind()
    reject_nonempty_downgrade(connection, TASKIQ_TABLE_NAMES_V1)
    op.execute(f"DELETE FROM {SCHEMA_V1}.schema_revision WHERE component = 'executor.taskiq'")
    for table in reversed(TASKIQ_TABLE_NAMES_V1):
        op.execute(f"DROP TABLE IF EXISTS {SCHEMA_V1}.{table}")

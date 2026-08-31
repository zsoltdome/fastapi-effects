"""Install the transactional command idempotency ledger.

Revision ID: 0004_commands
Revises: 0003_taskiq
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.postgres.migrations.frozen_v1 import (
    COMMAND_DDL_V1,
    COMMAND_TABLE_NAMES_V1,
    SCHEMA_V1,
    command_schema_sql_v1,
    command_trigger_sql_v1,
    role_names_v1,
)
from fastapi_mergen.postgres.migrations.safety import reject_nonempty_downgrade

revision = "0004_commands"
down_revision = "0003_taskiq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    config = op.get_context().config
    if config is None:
        raise RuntimeError("Alembic migration configuration is unavailable.")
    configured = role_names_v1(config)
    for statement in COMMAND_DDL_V1:
        op.execute(statement)
    for table in COMMAND_TABLE_NAMES_V1:
        op.execute(f"ALTER TABLE {SCHEMA_V1}.{table} OWNER TO {configured.migration}")
    for statement in command_trigger_sql_v1():
        op.execute(statement)
    op.execute(
        f"INSERT INTO {SCHEMA_V1}.schema_revision(component, revision, installed_at) "
        "VALUES ('commands', 1, CURRENT_TIMESTAMP) ON CONFLICT (component) "
        "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
    )
    for statement in command_schema_sql_v1(configured):
        op.execute(statement)


def downgrade() -> None:
    connection = op.get_bind()
    reject_nonempty_downgrade(connection, COMMAND_TABLE_NAMES_V1)
    op.execute(
        f"DROP FUNCTION IF EXISTS {SCHEMA_V1}.prune_commands(timestamp with time zone, integer)"
    )
    op.execute(f"DROP TRIGGER IF EXISTS guard_command_mutation ON {SCHEMA_V1}.commands")
    for table in reversed(COMMAND_TABLE_NAMES_V1):
        op.execute(f"DROP TABLE IF EXISTS {SCHEMA_V1}.{table}")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA_V1}.guard_command_mutation()")
    op.execute(f"DELETE FROM {SCHEMA_V1}.schema_revision WHERE component = 'commands'")

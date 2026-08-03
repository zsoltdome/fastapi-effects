"""Install the transactional command idempotency ledger.

Revision ID: 0004_commands
Revises: 0003_taskiq
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.idempotency.models import COMMAND_TABLES
from fastapi_mergen.postgres.command_schema import command_schema_sql, command_trigger_sql
from fastapi_mergen.postgres.migrations.safety import reject_nonempty_downgrade
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.sqlalchemy.models import SCHEMA

revision = "0004_commands"
down_revision = "0003_taskiq"
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
    for table in COMMAND_TABLES:
        table.create(connection, checkfirst=True)
        op.execute(f"ALTER TABLE {SCHEMA}.{table.name} OWNER TO {configured.migration}")
    for statement in command_trigger_sql():
        op.execute(statement)
    op.execute(
        f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
        "VALUES ('commands', 1, CURRENT_TIMESTAMP) ON CONFLICT (component) "
        "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
    )
    for statement in command_schema_sql(configured):
        op.execute(statement)


def downgrade() -> None:
    connection = op.get_bind()
    reject_nonempty_downgrade(connection, tuple(table.name for table in COMMAND_TABLES))
    op.execute(
        f"DROP FUNCTION IF EXISTS {SCHEMA}.prune_commands(timestamp with time zone, integer)"
    )
    op.execute(f"DROP TRIGGER IF EXISTS guard_command_mutation ON {SCHEMA}.commands")
    for table in reversed(COMMAND_TABLES):
        table.drop(connection, checkfirst=True)
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.guard_command_mutation()")
    op.execute(f"DELETE FROM {SCHEMA}.schema_revision WHERE component = 'commands'")

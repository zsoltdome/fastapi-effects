"""Install the core event, delivery, and attempt runtime.

Revision ID: 0001_core_runtime
Revises: None
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.postgres.migrations.safety import reject_nonempty_downgrade
from fastapi_mergen.postgres.rls import TENANT_TABLES, rls_sql
from fastapi_mergen.postgres.roles import (
    RuntimeRoles,
    create_role_sql,
)
from fastapi_mergen.sqlalchemy.models import CORE_TABLES, SCHEMA

revision = "0001_core_runtime"
down_revision = None
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
    if config.attributes.get("create_runtime_roles", True):
        for role in (configured.migration, configured.application, configured.relay):
            op.execute(create_role_sql(role))
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA} AUTHORIZATION {configured.migration}")
    for core_table in CORE_TABLES:
        core_table.create(connection, checkfirst=True)
    op.execute(f"ALTER SCHEMA {SCHEMA} OWNER TO {configured.migration}")
    for table in ("schema_revision", *TENANT_TABLES):
        op.execute(f"ALTER TABLE {SCHEMA}.{table} OWNER TO {configured.migration}")
    op.execute(
        f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
        "VALUES ('core', 1, CURRENT_TIMESTAMP) ON CONFLICT (component) "
        "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
    )
    for statement in rls_sql(configured):
        op.execute(statement)
    op.execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {configured.application}, {configured.relay}")
    op.execute(
        f"GRANT SELECT, INSERT ON {SCHEMA}.events, {SCHEMA}.deliveries TO {configured.application}"
    )
    op.execute(f"GRANT SELECT ON {SCHEMA}.attempts TO {configured.application}")
    op.execute(f"GRANT SELECT ON {SCHEMA}.events TO {configured.relay}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON {SCHEMA}.deliveries, {SCHEMA}.attempts "
        f"TO {configured.relay}"
    )
    op.execute(
        f"GRANT SELECT ON {SCHEMA}.schema_revision TO {configured.application}, {configured.relay}"
    )


def downgrade() -> None:
    connection = op.get_bind()
    reject_nonempty_downgrade(connection, ("events", "deliveries", "attempts"))
    for core_table in reversed(CORE_TABLES):
        core_table.drop(connection, checkfirst=True)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")

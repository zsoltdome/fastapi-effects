"""Install the core event, delivery, and attempt runtime.

Revision ID: 0001_core_runtime
Revises: None
"""

from __future__ import annotations

from alembic import op

from fastapi_mergen.postgres.migrations.frozen_v1 import (
    CORE_DDL_V1,
    CORE_TABLE_NAMES_V1,
    SCHEMA_V1,
    core_rls_sql_v1,
    create_role_sql_v1,
    role_names_v1,
)
from fastapi_mergen.postgres.migrations.safety import reject_nonempty_downgrade

revision = "0001_core_runtime"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    config = op.get_context().config
    if config is None:
        raise RuntimeError("Alembic migration configuration is unavailable.")
    configured = role_names_v1(config)
    if config.attributes.get("create_runtime_roles", True):
        for role in (configured.migration, configured.application, configured.relay):
            op.execute(create_role_sql_v1(role))
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_V1} AUTHORIZATION {configured.migration}")
    for statement in CORE_DDL_V1:
        op.execute(statement)
    op.execute(f"ALTER SCHEMA {SCHEMA_V1} OWNER TO {configured.migration}")
    for table in CORE_TABLE_NAMES_V1:
        op.execute(f"ALTER TABLE {SCHEMA_V1}.{table} OWNER TO {configured.migration}")
    op.execute(
        f"INSERT INTO {SCHEMA_V1}.schema_revision(component, revision, installed_at) "
        "VALUES ('core', 1, CURRENT_TIMESTAMP) ON CONFLICT (component) "
        "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
    )
    for statement in core_rls_sql_v1(configured):
        op.execute(statement)
    op.execute(f"REVOKE ALL ON SCHEMA {SCHEMA_V1} FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA_V1} TO {configured.application}, {configured.relay}")
    op.execute(
        f"GRANT SELECT, INSERT ON {SCHEMA_V1}.events, {SCHEMA_V1}.deliveries "
        f"TO {configured.application}"
    )
    op.execute(f"GRANT SELECT ON {SCHEMA_V1}.attempts TO {configured.application}")
    op.execute(f"GRANT SELECT ON {SCHEMA_V1}.events TO {configured.relay}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON {SCHEMA_V1}.deliveries, {SCHEMA_V1}.attempts "
        f"TO {configured.relay}"
    )
    op.execute(
        f"GRANT SELECT ON {SCHEMA_V1}.schema_revision TO "
        f"{configured.application}, {configured.relay}"
    )


def downgrade() -> None:
    connection = op.get_bind()
    reject_nonempty_downgrade(connection, ("events", "deliveries", "attempts"))
    for table in reversed(CORE_TABLE_NAMES_V1):
        op.execute(f"DROP TABLE IF EXISTS {SCHEMA_V1}.{table}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_V1}")

"""Canonical tenant row-security expressions and policy installers."""

from __future__ import annotations

from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.sqlalchemy.models import SCHEMA

TENANT_EXPRESSION = "tenant_id = nullif(current_setting('mergen.tenant_id', true), '')::uuid"
TENANT_TABLES = ("events", "deliveries", "attempts")


def rls_sql(roles: RuntimeRoles | None = None) -> tuple[str, ...]:
    configured = roles or RuntimeRoles()
    statements: list[str] = []
    for table in TENANT_TABLES:
        qualified = f"{SCHEMA}.{table}"
        statements.extend(
            (
                f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
                f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
                f"DROP POLICY IF EXISTS {table}_application_tenant ON {qualified}",
                (
                    f"CREATE POLICY {table}_application_tenant ON {qualified} "
                    f"FOR ALL TO {configured.application} USING ({TENANT_EXPRESSION}) "
                    f"WITH CHECK ({TENANT_EXPRESSION})"
                ),
                f"DROP POLICY IF EXISTS {table}_migration_control ON {qualified}",
                (
                    f"CREATE POLICY {table}_migration_control ON {qualified} "
                    f"FOR ALL TO {configured.migration} USING (true) WITH CHECK (true)"
                ),
            )
        )
    statements.extend(
        (
            f"DROP POLICY IF EXISTS events_relay_read ON {SCHEMA}.events",
            (
                f"CREATE POLICY events_relay_read ON {SCHEMA}.events "
                f"FOR SELECT TO {configured.relay} USING (true)"
            ),
            f"DROP POLICY IF EXISTS deliveries_relay_control ON {SCHEMA}.deliveries",
            (
                f"CREATE POLICY deliveries_relay_control ON {SCHEMA}.deliveries "
                f"FOR ALL TO {configured.relay} USING (true) WITH CHECK (true)"
            ),
            f"DROP POLICY IF EXISTS attempts_relay_control ON {SCHEMA}.attempts",
            (
                f"CREATE POLICY attempts_relay_control ON {SCHEMA}.attempts "
                f"FOR ALL TO {configured.relay} USING (true) WITH CHECK (true)"
            ),
        )
    )
    return tuple(statements)


__all__ = ["TENANT_EXPRESSION", "TENANT_TABLES", "rls_sql"]

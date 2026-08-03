"""Webhook schema installation, grants, forced RLS, and compatibility checks."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_mergen.errors import SchemaRevisionMismatch
from fastapi_mergen.postgres.rls import TENANT_EXPRESSION
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.sqlalchemy.models import SCHEMA
from fastapi_mergen.webhooks.models import WEBHOOK_TABLES

WEBHOOK_SCHEMA_REVISION = 2
WEBHOOK_TENANT_TABLES = (
    "webhook_subscriptions",
    "webhook_secret_sets",
    "webhook_secret_versions",
    "webhook_subscription_versions",
    "webhook_audit",
)


def webhook_rls_sql(roles: RuntimeRoles | None = None) -> tuple[str, ...]:
    configured = roles or RuntimeRoles()
    statements: list[str] = []
    for table in WEBHOOK_TENANT_TABLES:
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
    for table in (
        "webhook_subscriptions",
        "webhook_secret_sets",
        "webhook_secret_versions",
        "webhook_subscription_versions",
    ):
        qualified = f"{SCHEMA}.{table}"
        statements.extend(
            (
                f"DROP POLICY IF EXISTS {table}_relay_read ON {qualified}",
                (
                    f"CREATE POLICY {table}_relay_read ON {qualified} "
                    f"FOR SELECT TO {configured.relay} USING (true)"
                ),
            )
        )
    statements.extend(
        (
            (
                f"DROP POLICY IF EXISTS webhook_subscriptions_relay_health "
                f"ON {SCHEMA}.webhook_subscriptions"
            ),
            (
                f"CREATE POLICY webhook_subscriptions_relay_health "
                f"ON {SCHEMA}.webhook_subscriptions FOR UPDATE TO {configured.relay} "
                "USING (true) WITH CHECK (true)"
            ),
            f"DROP POLICY IF EXISTS webhook_audit_relay_append ON {SCHEMA}.webhook_audit",
            (
                f"CREATE POLICY webhook_audit_relay_append ON {SCHEMA}.webhook_audit "
                f"FOR INSERT TO {configured.relay} WITH CHECK (true)"
            ),
        )
    )
    return tuple(statements)


def webhook_grant_sql(roles: RuntimeRoles | None = None) -> tuple[str, ...]:
    configured = roles or RuntimeRoles()
    return (
        (
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.webhook_subscriptions, "
            f"{SCHEMA}.webhook_secret_sets, {SCHEMA}.webhook_secret_versions, "
            f"{SCHEMA}.webhook_subscription_versions TO {configured.application}"
        ),
        f"GRANT SELECT, INSERT ON {SCHEMA}.webhook_audit TO {configured.application}",
        (
            f"GRANT SELECT ON {SCHEMA}.webhook_secret_sets, "
            f"{SCHEMA}.webhook_secret_versions, {SCHEMA}.webhook_subscription_versions "
            f"TO {configured.relay}"
        ),
        (f"GRANT SELECT, UPDATE ON {SCHEMA}.webhook_subscriptions TO {configured.relay}"),
        f"GRANT INSERT ON {SCHEMA}.webhook_audit TO {configured.relay}",
    )


def webhook_retention_sql(roles: RuntimeRoles | None = None) -> tuple[str, ...]:
    """Create the bounded tenant-bound retention function and exact grants."""

    configured = roles or RuntimeRoles()
    signature = f"{SCHEMA}.prune_webhook_history(uuid, timestamp with time zone, integer)"
    return (
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA}.prune_webhook_history(
            requested_tenant uuid,
            cutoff timestamp with time zone,
            requested_batch integer
        ) RETURNS TABLE(
            attempts_deleted bigint,
            deliveries_deleted bigint,
            events_deleted bigint,
            secret_versions_deleted bigint
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, {SCHEMA}
        AS $retention$
        BEGIN
            IF nullif(current_setting('mergen.tenant_id', true), '')
                IS DISTINCT FROM requested_tenant::text THEN
                RAISE EXCEPTION 'webhook retention tenant context does not match'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF cutoff IS NULL OR requested_batch < 1 OR requested_batch > 10000 THEN
                RAISE EXCEPTION 'webhook retention arguments are invalid'
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;

            WITH locked AS (
                SELECT a.tenant_id, a.attempt_id
                FROM {SCHEMA}.attempts AS a
                JOIN {SCHEMA}.deliveries AS d
                  ON d.tenant_id = a.tenant_id AND d.delivery_id = a.delivery_id
                WHERE a.tenant_id = requested_tenant
                  AND a.finished_at < cutoff
                  AND d.destination_kind = 'webhook'
                  AND d.state IN ('succeeded', 'dead')
                  AND d.updated_at < cutoff
                ORDER BY a.finished_at, a.attempt_id
                LIMIT requested_batch FOR UPDATE OF a SKIP LOCKED
            ), deleted AS (
                DELETE FROM {SCHEMA}.attempts AS a
                USING locked
                WHERE a.tenant_id = locked.tenant_id
                  AND a.attempt_id = locked.attempt_id
                RETURNING 1
            )
            SELECT count(*) INTO attempts_deleted FROM deleted;

            WITH locked AS (
                SELECT d.tenant_id, d.delivery_id
                FROM {SCHEMA}.deliveries AS d
                WHERE d.tenant_id = requested_tenant
                  AND d.destination_kind = 'webhook'
                  AND d.state IN ('succeeded', 'dead')
                  AND d.updated_at < cutoff
                  AND NOT EXISTS (
                      SELECT 1 FROM {SCHEMA}.attempts AS a
                      WHERE a.tenant_id = d.tenant_id
                        AND a.delivery_id = d.delivery_id
                  )
                ORDER BY d.updated_at, d.delivery_id
                LIMIT requested_batch FOR UPDATE OF d SKIP LOCKED
            ), deleted AS (
                DELETE FROM {SCHEMA}.deliveries AS d
                USING locked
                WHERE d.tenant_id = locked.tenant_id
                  AND d.delivery_id = locked.delivery_id
                RETURNING 1
            )
            SELECT count(*) INTO deliveries_deleted FROM deleted;

            WITH locked AS (
                SELECT e.tenant_id, e.event_id
                FROM {SCHEMA}.events AS e
                WHERE e.tenant_id = requested_tenant
                  AND e.created_at < cutoff
                  AND NOT EXISTS (
                      SELECT 1 FROM {SCHEMA}.deliveries AS d
                      WHERE d.tenant_id = e.tenant_id AND d.event_id = e.event_id
                  )
                ORDER BY e.created_at, e.event_id
                LIMIT requested_batch FOR UPDATE OF e SKIP LOCKED
            ), deleted AS (
                DELETE FROM {SCHEMA}.events AS e
                USING locked
                WHERE e.tenant_id = locked.tenant_id
                  AND e.event_id = locked.event_id
                RETURNING 1
            )
            SELECT count(*) INTO events_deleted FROM deleted;

            WITH locked AS (
                SELECT s.tenant_id, s.secret_set_id, s.secret_version
                FROM {SCHEMA}.webhook_secret_versions AS s
                WHERE s.tenant_id = requested_tenant
                  AND s.state IN ('retiring', 'revoked')
                  AND s.created_at < cutoff
                ORDER BY s.created_at, s.secret_set_id, s.secret_version
                LIMIT requested_batch FOR UPDATE OF s SKIP LOCKED
            ), deleted AS (
                DELETE FROM {SCHEMA}.webhook_secret_versions AS s
                USING locked
                WHERE s.tenant_id = locked.tenant_id
                  AND s.secret_set_id = locked.secret_set_id
                  AND s.secret_version = locked.secret_version
                RETURNING 1
            )
            SELECT count(*) INTO secret_versions_deleted FROM deleted;
            RETURN NEXT;
        END
        $retention$
        """,
        f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC",
        f"REVOKE ALL ON FUNCTION {signature} FROM {configured.relay}",
        f"GRANT EXECUTE ON FUNCTION {signature} TO {configured.application}",
    )


async def install_webhook_schema(
    engine: AsyncEngine,
    *,
    roles: RuntimeRoles | None = None,
) -> None:
    configured = roles or RuntimeRoles()
    async with engine.begin() as connection:
        for table in WEBHOOK_TABLES:
            await connection.run_sync(table.create, checkfirst=True)
        await connection.execute(
            text(
                f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
                "VALUES ('webhooks', :revision, CURRENT_TIMESTAMP) ON CONFLICT (component) "
                "DO UPDATE SET revision = EXCLUDED.revision, installed_at = EXCLUDED.installed_at"
            ),
            {"revision": WEBHOOK_SCHEMA_REVISION},
        )
        for statement in (
            *webhook_rls_sql(configured),
            *webhook_grant_sql(configured),
            *webhook_retention_sql(configured),
        ):
            await connection.execute(text(statement))


async def check_webhook_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        actual = await connection.scalar(
            text(f"SELECT revision FROM {SCHEMA}.schema_revision WHERE component = 'webhooks'")
        )
    if actual != WEBHOOK_SCHEMA_REVISION:
        raise SchemaRevisionMismatch(
            component="webhooks",
            expected=WEBHOOK_SCHEMA_REVISION,
            actual=0 if actual is None else int(actual),
        )


__all__ = [
    "WEBHOOK_SCHEMA_REVISION",
    "WEBHOOK_TENANT_TABLES",
    "check_webhook_schema",
    "install_webhook_schema",
    "webhook_grant_sql",
    "webhook_retention_sql",
    "webhook_rls_sql",
]

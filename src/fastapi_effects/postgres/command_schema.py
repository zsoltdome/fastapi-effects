"""Command-ledger schema installation, immutability, RLS, and grants."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_effects.errors import SchemaRevisionMismatch
from fastapi_effects.idempotency.models import COMMAND_TABLES
from fastapi_effects.postgres.rls import TENANT_EXPRESSION
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.sqlalchemy.models import SCHEMA

COMMAND_SCHEMA_REVISION = 1


def command_trigger_sql() -> tuple[str, ...]:
    qualified = f"{SCHEMA}.commands"
    function = f"{SCHEMA}.guard_command_mutation"
    return (
        f"""
        CREATE OR REPLACE FUNCTION {function}() RETURNS trigger
        LANGUAGE plpgsql AS $guard$
        BEGIN
            IF ROW(
                NEW.tenant_id, NEW.command_id, NEW.route_id, NEW.method,
                NEW.key_digest, NEW.generation, NEW.subject_id,
                NEW.fingerprint_version, NEW.fingerprint, NEW.created_at, NEW.expires_at
            ) IS DISTINCT FROM ROW(
                OLD.tenant_id, OLD.command_id, OLD.route_id, OLD.method,
                OLD.key_digest, OLD.generation, OLD.subject_id,
                OLD.fingerprint_version, OLD.fingerprint, OLD.created_at, OLD.expires_at
            ) THEN
                RAISE EXCEPTION 'command immutable fields cannot change'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NOT (
                NEW.state = OLD.state OR
                (OLD.state = 'in_progress' AND NEW.state IN ('completed', 'superseded')) OR
                (OLD.state = 'completed' AND NEW.state = 'superseded')
            ) THEN
                RAISE EXCEPTION 'illegal command state transition'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.state = 'superseded' AND NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'superseded command history is immutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.state = 'completed' AND ROW(
                NEW.response_status, NEW.response_headers, NEW.response_body,
                NEW.response_media_type, NEW.completed_at
            ) IS DISTINCT FROM ROW(
                OLD.response_status, OLD.response_headers, OLD.response_body,
                OLD.response_media_type, OLD.completed_at
            ) THEN
                RAISE EXCEPTION 'completed command response is immutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END
        $guard$
        """,
        f"DROP TRIGGER IF EXISTS guard_command_mutation ON {qualified}",
        (
            f"CREATE TRIGGER guard_command_mutation BEFORE UPDATE ON {qualified} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        ),
    )


def command_schema_sql(roles: RuntimeRoles | None = None) -> tuple[str, ...]:
    configured = roles or RuntimeRoles()
    qualified = f"{SCHEMA}.commands"
    return (
        f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS commands_application_tenant ON {qualified}",
        (
            f"CREATE POLICY commands_application_tenant ON {qualified} "
            f"FOR ALL TO {configured.application} USING ({TENANT_EXPRESSION}) "
            f"WITH CHECK ({TENANT_EXPRESSION})"
        ),
        f"DROP POLICY IF EXISTS commands_relay_read ON {qualified}",
        (
            f"CREATE POLICY commands_relay_read ON {qualified} "
            f"FOR SELECT TO {configured.relay} USING (true)"
        ),
        f"DROP POLICY IF EXISTS commands_relay_delete ON {qualified}",
        (
            f"CREATE POLICY commands_relay_delete ON {qualified} "
            f"FOR DELETE TO {configured.relay} USING (true)"
        ),
        f"DROP POLICY IF EXISTS commands_migration_control ON {qualified}",
        (
            f"CREATE POLICY commands_migration_control ON {qualified} "
            f"FOR ALL TO {configured.migration} USING (true) WITH CHECK (true)"
        ),
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {qualified} TO {configured.application}",
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA}.prune_commands(
            cutoff timestamp with time zone, requested_batch integer
        ) RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, {SCHEMA}
        AS $prune$
        DECLARE deleted_count bigint;
        BEGIN
            IF requested_batch < 1 OR requested_batch > 10000 THEN
                RAISE EXCEPTION 'command pruning batch size is invalid'
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;
            WITH locked AS (
                SELECT ctid FROM {qualified}
                WHERE state IN ('completed', 'superseded') AND expires_at <= cutoff
                ORDER BY expires_at, command_id
                LIMIT requested_batch FOR UPDATE SKIP LOCKED
            ), deleted AS (
                DELETE FROM {qualified}
                WHERE ctid IN (SELECT ctid FROM locked)
                RETURNING 1
            )
            SELECT count(*) INTO deleted_count FROM deleted;
            RETURN deleted_count;
        END
        $prune$
        """,
        (
            f"REVOKE ALL ON FUNCTION {SCHEMA}.prune_commands"
            "(timestamp with time zone, integer) FROM PUBLIC"
        ),
        (
            f"GRANT EXECUTE ON FUNCTION {SCHEMA}.prune_commands"
            f"(timestamp with time zone, integer) TO {configured.relay}"
        ),
    )


async def install_command_schema(
    engine: AsyncEngine,
    *,
    roles: RuntimeRoles | None = None,
) -> None:
    configured = roles or RuntimeRoles()
    async with engine.begin() as connection:
        for table in COMMAND_TABLES:
            await connection.run_sync(table.create, checkfirst=True)
        for statement in command_trigger_sql():
            await connection.execute(text(statement))
        await connection.execute(
            text(
                f"INSERT INTO {SCHEMA}.schema_revision(component, revision, installed_at) "
                "VALUES ('commands', :revision, CURRENT_TIMESTAMP) "
                "ON CONFLICT (component) DO UPDATE SET revision = EXCLUDED.revision, "
                "installed_at = EXCLUDED.installed_at"
            ),
            {"revision": COMMAND_SCHEMA_REVISION},
        )
        for statement in command_schema_sql(configured):
            await connection.execute(text(statement))


async def check_command_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        actual = await connection.scalar(
            text(f"SELECT revision FROM {SCHEMA}.schema_revision WHERE component = 'commands'")
        )
    if actual != COMMAND_SCHEMA_REVISION:
        raise SchemaRevisionMismatch(
            component="commands",
            expected=COMMAND_SCHEMA_REVISION,
            actual=0 if actual is None else int(actual),
        )


__all__ = [
    "COMMAND_SCHEMA_REVISION",
    "check_command_schema",
    "command_schema_sql",
    "command_trigger_sql",
    "install_command_schema",
]

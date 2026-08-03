from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine

from fastapi_mergen.errors import SchemaRevisionMismatch
from fastapi_mergen.postgres.revisions import (
    MIGRATION_HEAD,
    SCHEMA_REVISION_REGISTRY,
    check_schema_revisions,
)
from fastapi_mergen.postgres.roles import RuntimeRoles
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration

MIGRATIONS = (
    Path(__file__).resolve().parents[2] / "src" / "fastapi_mergen" / "postgres" / "migrations"
)
REVISIONS = (
    "0001_core_runtime",
    "0002_webhooks",
    "0003_taskiq",
    "0004_commands",
    "0005_webhook_retention",
)
TABLES = (
    "events",
    "deliveries",
    "attempts",
    "webhook_secret_sets",
    "webhook_subscriptions",
    "webhook_secret_versions",
    "webhook_subscription_versions",
    "webhook_audit",
    "taskiq_handoffs",
    "commands",
)


def _run_revision(
    connection: Connection,
    revision: str,
    roles: RuntimeRoles,
    *,
    downgrade: bool = False,
) -> None:
    configuration = Config(str(MIGRATIONS / "alembic.ini"))
    configuration.set_main_option("script_location", str(MIGRATIONS))
    configuration.attributes["connection"] = connection
    configuration.attributes["runtime_roles"] = roles
    configuration.attributes["create_runtime_roles"] = False
    if downgrade:
        command.downgrade(configuration, revision)
    else:
        command.upgrade(configuration, revision)


def _seed_revision(connection: Connection, revision: str) -> tuple[str, ...]:
    now = datetime.now(UTC)
    tenant = uuid4()
    event = uuid4()
    delivery = uuid4()
    attempt = uuid4()
    lease = uuid4()
    secret_set = uuid4()
    subscription = uuid4()
    common = {
        "tenant": tenant,
        "now": now,
        "event": event,
        "delivery": delivery,
        "attempt": attempt,
        "lease": lease,
    }
    connection.execute(
        text(
            "INSERT INTO fastapi_mergen.events "
            "(tenant_id,event_id,event_type,event_version,canonical_version,payload,"
            "payload_canonical,payload_sha256,principal,occurred_at,created_at) VALUES "
            "(:tenant,:event,'migration.probe',1,1,CAST('{}' AS jsonb),:canonical,:digest,"
            "CAST(:principal AS jsonb),:now,:now)"
        ),
        {
            **common,
            "canonical": b"fastapi-mergen:canonical-json:v1\n{}",
            "digest": bytes(32),
            "principal": (
                '{"tenant_id":"' + str(tenant) + '","subject_id":"migration-probe","scopes":[]}'
            ),
        },
    )
    connection.execute(
        text(
            "INSERT INTO fastapi_mergen.deliveries "
            "(tenant_id,delivery_id,event_id,route_key,route_version,destination_kind,"
            "destination_key,route_snapshot,route_snapshot_bytes,state,attempts_started,"
            "next_attempt_at,created_at,updated_at) VALUES "
            "(:tenant,:delivery,:event,'migration.probe',1,'handler','probe',"
            "CAST('{}' AS jsonb),:snapshot,'succeeded',1,:now,:now,:now)"
        ),
        {**common, "snapshot": b"{}"},
    )
    connection.execute(
        text(
            "INSERT INTO fastapi_mergen.attempts "
            "(tenant_id,attempt_id,delivery_id,attempt_number,lease_token,outcome,started_at,"
            "finished_at) VALUES (:tenant,:attempt,:delivery,1,:lease,'succeeded',:now,:now)"
        ),
        common,
    )
    seeded = ["events", "deliveries", "attempts"]

    if revision >= "0002_webhooks":
        connection.execute(
            text(
                "INSERT INTO fastapi_mergen.webhook_secret_sets "
                "(tenant_id,secret_set_id,revision,created_by,created_at,updated_at) "
                "VALUES (:tenant,:secret_set,1,'migration-probe',:now,:now)"
            ),
            {**common, "secret_set": secret_set},
        )
        connection.execute(
            text(
                "INSERT INTO fastapi_mergen.webhook_subscriptions "
                "(tenant_id,subscription_id,current_version,revision,state,failure_streak,"
                "auto_pause_threshold,created_by,updated_by,created_at,updated_at) VALUES "
                "(:tenant,:subscription,1,1,'active',0,20,'migration-probe',"
                "'migration-probe',:now,:now)"
            ),
            {**common, "subscription": subscription},
        )
        connection.execute(
            text(
                "INSERT INTO fastapi_mergen.webhook_secret_versions "
                "(tenant_id,secret_set_id,secret_version,key_id,nonce,ciphertext,state,created_at) "
                "VALUES (:tenant,:secret_set,1,'migration-key',:nonce,:ciphertext,'active',:now)"
            ),
            {
                **common,
                "secret_set": secret_set,
                "nonce": bytes(12),
                "ciphertext": bytes(16),
            },
        )
        connection.execute(
            text(
                "INSERT INTO fastapi_mergen.webhook_subscription_versions "
                "(tenant_id,subscription_id,version,exact_event_types,endpoint_url,retry_policy,"
                "secret_set_id,created_by,created_at) VALUES "
                "(:tenant,:subscription,1,CAST('[\"migration.probe\"]' AS jsonb),"
                "'https://example.test/hook',CAST('{}' AS jsonb),:secret_set,"
                "'migration-probe',:now)"
            ),
            {**common, "subscription": subscription, "secret_set": secret_set},
        )
        connection.execute(
            text(
                "INSERT INTO fastapi_mergen.webhook_audit "
                "(tenant_id,audit_id,subject_id,action,target_kind,target_id,details,occurred_at) "
                "VALUES (:tenant,:audit,'migration-probe','created','subscription',"
                ":subscription,CAST('{}' AS jsonb),:now)"
            ),
            {**common, "audit": uuid4(), "subscription": subscription},
        )
        seeded.extend(
            (
                "webhook_secret_sets",
                "webhook_subscriptions",
                "webhook_secret_versions",
                "webhook_subscription_versions",
                "webhook_audit",
            )
        )

    if revision >= "0003_taskiq":
        connection.execute(
            text(
                "INSERT INTO fastapi_mergen.taskiq_handoffs "
                "(tenant_id,handoff_id,delivery_id,attempt_id,task_id,handoff_token,state,"
                "principal,route_snapshot,route_snapshot_bytes,event_metadata,execution_count,"
                "prepared_at,enqueued_at,finished_at,updated_at) VALUES "
                "(:tenant,:handoff,:delivery,:attempt,'migration-task',:handoff_token,"
                "'succeeded',CAST('{}' AS jsonb),CAST('{}' AS jsonb),:snapshot,"
                "CAST('{}' AS jsonb),1,:now,:now,:now,:now)"
            ),
            {
                **common,
                "handoff": uuid4(),
                "handoff_token": uuid4(),
                "snapshot": b"{}",
            },
        )
        seeded.append("taskiq_handoffs")

    if revision >= "0004_commands":
        connection.execute(
            text(
                "INSERT INTO fastapi_mergen.commands "
                "(tenant_id,command_id,route_id,method,key_digest,generation,is_current,"
                "subject_id,fingerprint_version,fingerprint,state,response_status,"
                "response_headers,response_body,response_media_type,created_at,updated_at,"
                "expires_at,completed_at) VALUES "
                "(:tenant,:command,'migration.probe','POST',:digest,1,true,'migration-probe',"
                "1,:digest,'completed',200,CAST('{}' AS jsonb),:body,'application/json',"
                ":now,:now,:expires,:now)"
            ),
            {
                **common,
                "command": uuid4(),
                "digest": bytes(32),
                "body": b"{}",
                "expires": now + timedelta(days=1),
            },
        )
        seeded.append("commands")
    return tuple(seeded)


@pytest.mark.parametrize("revision", REVISIONS)
@pytest.mark.asyncio
async def test_every_published_revision_upgrades_to_head_without_data_loss(
    test_database: ProvisionedDatabase,
    revision: str,
) -> None:
    engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_run_revision, revision, roles)
            seeded = await connection.run_sync(_seed_revision, revision)
            await connection.run_sync(_run_revision, MIGRATION_HEAD, roles)
        await check_schema_revisions(engine)
        async with engine.connect() as connection:
            for table in seeded:
                count = await connection.scalar(
                    text(f"SELECT count(*) FROM fastapi_mergen.{table}")
                )
                assert count == 1
            installed = (
                await connection.execute(
                    text("SELECT component, revision FROM fastapi_mergen.schema_revision")
                )
            ).all()
            revision_rows = {str(row.component): int(row.revision) for row in installed}
            assert revision_rows == dict(SCHEMA_REVISION_REGISTRY)
            rows = (
                await connection.execute(
                    text(
                        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                        "pg_get_userbyid(c.relowner) FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'fastapi_mergen' AND c.relname = ANY(:tables)"
                    ),
                    {"tables": list(TABLES)},
                )
            ).all()
            assert {str(row[0]) for row in rows} == set(TABLES)
            assert all(str(row[3]) == test_database.migration_role for row in rows)
            assert all(bool(row[1]) and bool(row[2]) for row in rows)
            trigger_enabled = await connection.scalar(
                text(
                    "SELECT tgenabled = 'O' FROM pg_trigger WHERE tgname = 'guard_command_mutation'"
                )
            )
            assert trigger_enabled is True
            retention_function = (
                await connection.execute(
                    text(
                        "SELECT p.prosecdef, pg_get_userbyid(p.proowner), p.proconfig "
                        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                        "WHERE n.nspname = 'fastapi_mergen' "
                        "AND p.proname = 'prune_webhook_history'"
                    )
                )
            ).one()
            assert retention_function.prosecdef is True
            assert retention_function[1] == test_database.migration_role
            assert retention_function.proconfig == ["search_path=pg_catalog, fastapi_mergen"]
            signature = (
                "fastapi_mergen.prune_webhook_history(uuid,timestamp with time zone,integer)"
            )
            application_can_execute = await connection.scalar(
                text("SELECT has_function_privilege(:role, :signature, 'EXECUTE')"),
                {"role": test_database.app_role, "signature": signature},
            )
            relay_can_execute = await connection.scalar(
                text("SELECT has_function_privilege(:role, :signature, 'EXECUTE')"),
                {"role": test_database.relay_role, "signature": signature},
            )
            public_can_execute = await connection.scalar(
                text("SELECT has_function_privilege('public', :signature, 'EXECUTE')"),
                {"signature": signature},
            )
            assert application_can_execute is True
            assert relay_can_execute is False
            assert public_can_execute is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_schema_gate_rejects_older_and_newer_revisions(
    test_database: ProvisionedDatabase,
) -> None:
    engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_run_revision, "0001_core_runtime", roles)
        with pytest.raises(SchemaRevisionMismatch) as older:
            await check_schema_revisions(engine)
        assert older.value.component == "webhooks"
        assert older.value.actual == 0

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE fastapi_mergen.schema_revision SET revision = 2 "
                    "WHERE component = 'core'"
                )
            )
        with pytest.raises(SchemaRevisionMismatch) as newer:
            await check_schema_revisions(engine, components=("core",))
        assert newer.value.expected == 1
        assert newer.value.actual == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_destructive_downgrade_rejects_nonempty_component(
    test_database: ProvisionedDatabase,
) -> None:
    engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_run_revision, MIGRATION_HEAD, roles)
            await connection.run_sync(_seed_revision, MIGRATION_HEAD)
        with pytest.raises(Exception, match="Refusing destructive downgrade"):
            async with engine.begin() as connection:
                await connection.run_sync(_run_revision, "0003_taskiq", roles, downgrade=True)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_retention_revision_downgrade_preserves_data(
    test_database: ProvisionedDatabase,
) -> None:
    engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_run_revision, MIGRATION_HEAD, roles)
            seeded = await connection.run_sync(_seed_revision, MIGRATION_HEAD)
            await connection.run_sync(
                _run_revision,
                "0004_commands",
                roles,
                downgrade=True,
            )
            function_exists = await connection.scalar(
                text(
                    "SELECT to_regprocedure('fastapi_mergen.prune_webhook_history"
                    "(uuid,timestamp with time zone,integer)') IS NOT NULL"
                )
            )
            webhook_revision = await connection.scalar(
                text(
                    "SELECT revision FROM fastapi_mergen.schema_revision "
                    "WHERE component = 'webhooks'"
                )
            )
            for table in seeded:
                count = await connection.scalar(
                    text(f"SELECT count(*) FROM fastapi_mergen.{table}")
                )
                assert count == 1
        assert function_exists is False
        assert webhook_revision == 1
    finally:
        await engine.dispose()

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest
from scripts.verify_restore import compare_restore
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_effects import Principal
from fastapi_effects.conformance import (
    CertificationProfile,
    ConformanceRunner,
    RunnerConfiguration,
)
from fastapi_effects.conformance.protocols import BoundaryDriver
from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.observability.events import RuntimeEvent, RuntimeEventKind
from fastapi_effects.observability.postgres import observe_backlog
from fastapi_effects.postgres.diagnostics import inspect_runtime_database
from fastapi_effects.postgres.revisions import check_schema_revisions
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import install_core_schema
from fastapi_effects.postgres.webhook_schema import install_webhook_schema
from fastapi_effects.testing.delegation_driver import RealDelegationBoundaryDriver
from fastapi_effects.testing.idempotency_driver import PostgresIdempotencyBoundaryDriver
from fastapi_effects.testing.postgres_driver import PostgresBoundaryDriver
from fastapi_effects.testing.taskiq_driver import PostgresTaskiqBoundaryDriver
from fastapi_effects.testing.webhook_driver import PostgresWebhookBoundaryDriver
from fastapi_effects.webhooks.operations import RetentionResult, WebhookOperations
from fastapi_effects.webhooks.secrets import (
    MasterKey,
    StaticMasterKeyProvider,
    WebhookSecretService,
)
from fastapi_effects.webhooks.subscriptions import SubscriptionRepository
from tests.integration.postgres import ProvisionedDatabase, provision_test_database
from tests.migrations.test_revision_matrix import MIGRATION_HEAD, _run_revision, _seed_revision

pytestmark = pytest.mark.integration


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def record(self, event: RuntimeEvent) -> None:
        self.events.append(event)


async def _run_postgres_tool(*command: str) -> None:
    process = await asyncio.create_subprocess_exec(*command)
    return_code = await process.wait()
    if return_code != 0:
        raise RuntimeError(f"PostgreSQL client exited with status {return_code}.")


def _admin_database_dsn(admin_dsn: str, database: str) -> str:
    parsed = urlsplit(admin_dsn)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", parsed.query, ""))


async def _assert_certified(profile: CertificationProfile, driver: BoundaryDriver) -> None:
    report = await ConformanceRunner(RunnerConfiguration(profile=profile)).run(driver)
    failures = [
        f"{result.check_id}: {result.status.value} ({result.exception_type})"
        for result in report.results
        if result.status.value not in {"passed", "not_applicable"}
    ]
    assert report.certified, "\n".join(failures)


async def _certify_restored_database(
    *,
    migration_engine: AsyncEngine,
    application_engine: AsyncEngine,
    relay_engine: AsyncEngine,
    roles: RuntimeRoles,
) -> None:
    for profile in (
        CertificationProfile.CORE,
        CertificationProfile.DELIVERY,
        CertificationProfile.SECURITY,
    ):
        await _assert_certified(
            profile,
            await PostgresBoundaryDriver.create(
                migration_engine=migration_engine,
                app_engine=application_engine,
                relay_engine=relay_engine,
                roles=roles,
            ),
        )
    await _assert_certified(
        CertificationProfile.WEBHOOK,
        await PostgresWebhookBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=application_engine,
            relay_engine=relay_engine,
            roles=roles,
        ),
    )
    await _assert_certified(
        CertificationProfile.COMMAND,
        await PostgresIdempotencyBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=application_engine,
            relay_engine=relay_engine,
            roles=roles,
        ),
    )
    await _assert_certified(
        CertificationProfile.EXECUTOR,
        await PostgresTaskiqBoundaryDriver.create(
            migration_engine=migration_engine,
            app_engine=application_engine,
            relay_engine=relay_engine,
            roles=roles,
        ),
    )
    await _assert_certified(
        CertificationProfile.DELEGATION,
        RealDelegationBoundaryDriver(),
    )


async def _seed_retention_tenant(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    old: datetime,
    terminal: int,
    pending: int,
    include_secret_versions: bool,
) -> None:
    event_rows: list[dict[str, object]] = []
    delivery_rows: list[dict[str, object]] = []
    attempt_rows: list[dict[str, object]] = []
    for index in range(terminal + pending):
        event_id = uuid4()
        delivery_id = uuid4()
        is_terminal = index < terminal
        event_rows.append(
            {
                "tenant": tenant_id,
                "event": event_id,
                "canonical": b"fastapi_effects:canonical-json:v1\n{}",
                "digest": bytes(32),
                "principal": (
                    '{"tenant_id":"' + str(tenant_id) + '","subject_id":"retention","scopes":[]}'
                ),
                "old": old,
            }
        )
        delivery_rows.append(
            {
                "tenant": tenant_id,
                "delivery": delivery_id,
                "event": event_id,
                "route": f"retention.{index}",
                "destination": f"webhook.{index}",
                "snapshot": b"{}",
                "state": "succeeded" if is_terminal else "pending",
                "attempts": 1 if is_terminal else 0,
                "old": old,
            }
        )
        if is_terminal:
            attempt_rows.append(
                {
                    "tenant": tenant_id,
                    "attempt": uuid4(),
                    "delivery": delivery_id,
                    "lease": uuid4(),
                    "old": old,
                }
            )
    async with engine.begin() as connection:
        if event_rows:
            await connection.execute(
                text(
                    "INSERT INTO fastapi_effects.events "
                    "(tenant_id,event_id,event_type,event_version,canonical_version,payload,"
                    "payload_canonical,payload_sha256,principal,occurred_at,created_at) VALUES "
                    "(:tenant,:event,'retention.probe',1,1,CAST('{}' AS jsonb),:canonical,"
                    ":digest,CAST(:principal AS jsonb),:old,:old)"
                ),
                event_rows,
            )
            await connection.execute(
                text(
                    "INSERT INTO fastapi_effects.deliveries "
                    "(tenant_id,delivery_id,event_id,route_key,route_version,destination_kind,"
                    "destination_key,route_snapshot,route_snapshot_bytes,state,attempts_started,"
                    "next_attempt_at,created_at,updated_at) VALUES "
                    "(:tenant,:delivery,:event,:route,1,'webhook',:destination,"
                    "CAST('{}' AS jsonb),:snapshot,:state,:attempts,:old,:old,:old)"
                ),
                delivery_rows,
            )
        if attempt_rows:
            await connection.execute(
                text(
                    "INSERT INTO fastapi_effects.attempts "
                    "(tenant_id,attempt_id,delivery_id,attempt_number,lease_token,outcome,"
                    "started_at,finished_at) VALUES "
                    "(:tenant,:attempt,:delivery,1,:lease,'succeeded',:old,:old)"
                ),
                attempt_rows,
            )
        if include_secret_versions:
            secret_set = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO fastapi_effects.webhook_secret_sets "
                    "(tenant_id,secret_set_id,revision,created_by,created_at,updated_at) "
                    "VALUES (:tenant,:secret_set,2,'retention',:old,:old)"
                ),
                {"tenant": tenant_id, "secret_set": secret_set, "old": old},
            )
            for version, state, created_at in (
                (1, "revoked", old),
                (2, "active", datetime.now(UTC)),
            ):
                await connection.execute(
                    text(
                        "INSERT INTO fastapi_effects.webhook_secret_versions "
                        "(tenant_id,secret_set_id,secret_version,key_id,nonce,ciphertext,state,"
                        "created_at,revoked_at) VALUES "
                        "(:tenant,:secret_set,:version,'retention-key',:nonce,:ciphertext,"
                        ":state,:created_at,:revoked_at)"
                    ),
                    {
                        "tenant": tenant_id,
                        "secret_set": secret_set,
                        "version": version,
                        "nonce": bytes(12),
                        "ciphertext": bytes(16),
                        "state": state,
                        "created_at": created_at,
                        "revoked_at": old if state == "revoked" else None,
                    },
                )


async def _attempt_cross_tenant_retention(
    session: AsyncSession,
    *,
    context_tenant: UUID,
    requested_tenant: UUID,
    cutoff: datetime,
) -> None:
    async with session.begin():
        await session.execute(
            text("SELECT set_config('fastapi_effects.tenant_id', :tenant, true)"),
            {"tenant": str(context_tenant)},
        )
        await session.execute(
            text("SELECT * FROM fastapi_effects.prune_webhook_history(:tenant, :cutoff, 1)"),
            {"tenant": requested_tenant, "cutoff": cutoff},
        )


@pytest.mark.asyncio
async def test_logical_backup_restore_preserves_all_runtime_identity(
    postgres_admin_dsn: str,
    test_database: ProvisionedDatabase,
    tmp_path: Path,
) -> None:
    if shutil.which("pg_dump") is None or shutil.which("psql") is None:
        pytest.skip("PostgreSQL client tools are unavailable")
    source_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    source_roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    archive = tmp_path / "fastapi_effects.sql"
    try:
        async with source_engine.begin() as connection:
            await connection.run_sync(_run_revision, MIGRATION_HEAD, source_roles)
            await connection.run_sync(_seed_revision, MIGRATION_HEAD)
        await _run_postgres_tool(
            "pg_dump",
            "--format=plain",
            "--data-only",
            "--inserts",
            "--no-owner",
            "--schema=fastapi_effects",
            f"--file={archive}",
            _admin_database_dsn(test_database.admin_dsn, test_database.database),
        )
        dump_text = archive.read_text(encoding="utf-8")
        archive.write_text(
            "\n".join(
                "SET row_security = on;" if line == "SET row_security = off;" else line
                for line in dump_text.splitlines()
                if not line.startswith("SET transaction_timeout")
            )
            + "\n",
            encoding="utf-8",
        )
        async with provision_test_database(postgres_admin_dsn) as restored_database:
            restored_engine = create_async_engine(restored_database.migration_sqlalchemy_dsn)
            restored_application = create_async_engine(restored_database.app_sqlalchemy_dsn)
            restored_relay = create_async_engine(restored_database.relay_sqlalchemy_dsn)
            restored_roles = RuntimeRoles(
                migration=restored_database.migration_role,
                application=restored_database.app_role,
                relay=restored_database.relay_role,
            )
            try:
                async with restored_engine.begin() as connection:
                    await connection.run_sync(_run_revision, MIGRATION_HEAD, restored_roles)
                    await connection.execute(
                        text(
                            "TRUNCATE fastapi_effects.schema_revision, "
                            "fastapi_effects.events, fastapi_effects.deliveries, "
                            "fastapi_effects.attempts, fastapi_effects.webhook_secret_sets, "
                            "fastapi_effects.webhook_subscriptions, "
                            "fastapi_effects.webhook_secret_versions, "
                            "fastapi_effects.webhook_subscription_versions, "
                            "fastapi_effects.webhook_audit, fastapi_effects.taskiq_handoffs, "
                            "fastapi_effects.commands CASCADE"
                        )
                    )
                await _run_postgres_tool(
                    "psql",
                    "--set=ON_ERROR_STOP=1",
                    f"--dbname={restored_database.migration_dsn}",
                    f"--file={archive}",
                )
                await check_schema_revisions(restored_engine)
                identities = await compare_restore(
                    test_database.migration_dsn,
                    restored_database.migration_dsn,
                )
                assert all(identity.rows >= 1 for identity in identities.values())
                doctor = await inspect_runtime_database(
                    restored_application,
                    expected_role=restored_database.app_role,
                    roles=restored_roles,
                )
                assert doctor.healthy, doctor.checks
                sink = _RecordingSink()
                assert await observe_backlog(restored_relay, sink) == 0.0
                assert [event.kind for event in sink.events] == [RuntimeEventKind.BACKLOG_OBSERVED]
                async with restored_engine.begin() as connection:
                    for table in (
                        "taskiq_handoffs",
                        "commands",
                        "attempts",
                        "deliveries",
                        "events",
                    ):
                        await connection.execute(text(f"DELETE FROM fastapi_effects.{table}"))
                await _certify_restored_database(
                    migration_engine=restored_engine,
                    application_engine=restored_application,
                    relay_engine=restored_relay,
                    roles=restored_roles,
                )
                await check_schema_revisions(restored_engine)
            finally:
                await restored_relay.dispose()
                await restored_application.dispose()
                await restored_engine.dispose()
    finally:
        await source_engine.dispose()


@pytest.mark.asyncio
async def test_webhook_retention_is_bounded_resumable_tenant_safe_and_observable(
    test_database: ProvisionedDatabase,
) -> None:
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    application_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    application_sessions = async_sessionmaker(application_engine, expire_on_commit=False)
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    old = datetime.now(UTC) - timedelta(days=30)
    cutoff = datetime.now(UTC) - timedelta(days=7)
    principal = Principal(
        tenant_id=tenant_id,
        subject_id="operator:retention",
        scopes=frozenset({"webhooks:manage"}),
    )
    events = _RecordingSink()
    operations = WebhookOperations(
        subscriptions=SubscriptionRepository(),
        secrets=WebhookSecretService(
            StaticMasterKeyProvider(
                keys=(MasterKey("retention-key", b"r" * 32),),
                current_key_id="retention-key",
            )
        ),
        event_sink=events,
    )
    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_webhook_schema(migration_engine, roles=roles)
        await _seed_retention_tenant(
            migration_engine,
            tenant_id=tenant_id,
            old=old,
            terminal=1_000,
            pending=1,
            include_secret_versions=True,
        )
        await _seed_retention_tenant(
            migration_engine,
            tenant_id=other_tenant_id,
            old=old,
            terminal=1,
            pending=0,
            include_secret_versions=False,
        )

        async with application_sessions() as session, session.begin():
            with pytest.raises(FastAPIEffectsConfigurationError, match="idle session"):
                await operations.retain(
                    session,
                    principal=principal,
                    before=cutoff,
                    batch_size=128,
                )

        async with application_sessions() as session:
            with pytest.raises(DBAPIError):
                await _attempt_cross_tenant_retention(
                    session,
                    context_tenant=tenant_id,
                    requested_tenant=other_tenant_id,
                    cutoff=cutoff,
                )

        batch_size = 128
        results: list[RetentionResult] = []
        for _ in range(16):
            async with application_sessions() as session:
                result = await operations.retain(
                    session,
                    principal=principal,
                    before=cutoff,
                    batch_size=batch_size,
                )
            results.append(result)
            if result == RetentionResult(0, 0, 0, 0):
                break
        assert results[-1] == RetentionResult(0, 0, 0, 0)
        assert sum(result.attempts for result in results) == 1_000
        assert sum(result.deliveries for result in results) == 1_000
        assert sum(result.events for result in results) == 1_000
        assert sum(result.secret_versions for result in results) == 1
        assert all(
            max(
                result.attempts,
                result.deliveries,
                result.events,
                result.secret_versions,
            )
            <= batch_size
            for result in results
        )

        async with migration_engine.connect() as connection:
            tenant_count_values: list[int] = []
            other_count_values: list[int] = []
            for table in ("events", "deliveries", "attempts"):
                tenant_count_values.append(
                    int(
                        await connection.scalar(
                            text(
                                f"SELECT count(*) FROM fastapi_effects.{table} "
                                "WHERE tenant_id = :tenant"
                            ),
                            {"tenant": tenant_id},
                        )
                        or 0
                    )
                )
                other_count_values.append(
                    int(
                        await connection.scalar(
                            text(
                                f"SELECT count(*) FROM fastapi_effects.{table} "
                                "WHERE tenant_id = :tenant"
                            ),
                            {"tenant": other_tenant_id},
                        )
                        or 0
                    )
                )
            tenant_counts = tuple(tenant_count_values)
            other_counts = tuple(other_count_values)
            secret_states = tuple(
                (
                    await connection.scalars(
                        text(
                            "SELECT state FROM fastapi_effects.webhook_secret_versions "
                            "WHERE tenant_id = :tenant ORDER BY secret_version"
                        ),
                        {"tenant": tenant_id},
                    )
                ).all()
            )
        assert tenant_counts == (1, 1, 0)
        assert other_counts == (1, 1, 1)
        assert secret_states == ("active",)
        assert len(events.events) == len(results)
        assert all(event.kind is RuntimeEventKind.WEBHOOK_PRUNED for event in events.events)
        assert [event.attributes["pruned.count"] for event in events.events] == [
            result.attempts + result.deliveries + result.events + result.secret_versions
            for result in results
        ]
    finally:
        await application_engine.dispose()
        await migration_engine.dispose()

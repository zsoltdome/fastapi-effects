#!/usr/bin/env python3
"""Upgrade a database created by the public release wheel with the candidate wheel."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from fastapi_effects.postgres.revisions import MIGRATION_HEAD, SCHEMA_REVISION_REGISTRY

ROOT = Path(__file__).resolve().parents[1]
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_RUNTIME_ROLES = (
    "fastapi_effects_migration",
    "fastapi_effects_app",
    "fastapi_effects_relay",
)
_BASELINE_REVISIONS = {
    "commands": 1,
    "core": 1,
    "executor.taskiq": 1,
    "webhooks": 2,
}
_SEEDED_TABLES = (
    "attempts",
    "commands",
    "deliveries",
    "events",
    "taskiq_handoffs",
    "webhook_audit",
    "webhook_secret_sets",
    "webhook_secret_versions",
    "webhook_subscription_versions",
    "webhook_subscriptions",
)
_CHECKS = (
    "historical_artifact_digest",
    "historical_artifact_installed",
    "historical_schema_created",
    "historical_data_seeded",
    "candidate_artifact_installed",
    "candidate_schema_upgraded",
    "seeded_data_preserved",
    "ownership_preserved",
    "runtime_roles_preserved",
    "grants_preserved",
    "forced_rls_preserved",
    "constraints_preserved",
    "indexes_preserved",
    "revision_markers_current",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def load_historical_wheel(inventory_path: Path) -> dict[str, object]:
    value = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise ValueError("Release inventory must use schema version 2.")
    version = value.get("version")
    artifacts = value.get("artifacts")
    if not isinstance(version, str) or not version or not isinstance(artifacts, list):
        raise ValueError("Release inventory has no versioned artifact set.")
    wheels = [item for item in artifacts if isinstance(item, dict) and item.get("kind") == "wheel"]
    if len(wheels) != 1:
        raise ValueError("Release inventory must contain exactly one historical wheel.")
    wheel = wheels[0]
    filename = wheel.get("filename")
    url = wheel.get("url")
    digest = wheel.get("sha256")
    parsed = urlsplit(str(url))
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or not filename.endswith(".whl")
        or parsed.scheme != "https"
        or parsed.hostname != "files.pythonhosted.org"
        or not isinstance(digest, str)
        or _DIGEST.fullmatch(digest) is None
    ):
        raise ValueError("Historical wheel identity is unsafe or incomplete.")
    return {
        "version": version,
        "filename": filename,
        "url": str(url),
        "sha256": digest,
    }


def download_historical_wheel(identity: Mapping[str, object], output: Path) -> None:
    request = urllib.request.Request(
        str(identity["url"]), headers={"User-Agent": "fastapi-effects-release-gate"}
    )
    with urllib.request.urlopen(request, timeout=30) as response, output.open("wb") as stream:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname != "files.pythonhosted.org":
            raise ValueError("Historical wheel download escaped the approved PyPI host.")
        shutil.copyfileobj(response, stream, length=1024 * 1024)
    if sha256_file(output) != identity["sha256"]:
        raise ValueError("Historical wheel digest does not match the release inventory.")


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment.pop("VIRTUAL_ENV", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    environment.setdefault(
        "UV_CACHE_DIR",
        str(Path(tempfile.gettempdir()) / "fastapi_effects_uv-cache"),
    )
    return environment


def run(*command: str, cwd: Path, environment: Mapping[str, str] | None = None) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(
        command,
        cwd=cwd,
        env=dict(environment) if environment is not None else clean_environment(),
        check=True,
    )


def create_artifact_environment(
    path: Path,
    artifact: Path,
    *,
    constraints: Path,
    cwd: Path,
) -> Path:
    if shutil.which("uv") is None:
        raise RuntimeError("The historical upgrade gate requires uv.")
    run("uv", "venv", "--python", sys.executable, str(path), cwd=cwd)
    python = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--constraint",
        str(constraints),
        str(artifact),
        "asyncpg>=0.31,<1",
        cwd=cwd,
    )
    return python


def dsn_for_database(admin_dsn: str, database: str, *, sqlalchemy: bool = False) -> str:
    parsed = urlsplit(admin_dsn)
    base_scheme = parsed.scheme.split("+", 1)[0]
    if base_scheme not in {"postgres", "postgresql"}:
        raise ValueError("Upgrade target DSN must use postgres or postgresql.")
    scheme = "postgresql+asyncpg" if sqlalchemy else "postgresql"
    return urlunsplit((scheme, parsed.netloc, f"/{database}", parsed.query, ""))


def quote_identifier(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("Generated PostgreSQL identifier is unsafe.")
    return f'"{value}"'


def records(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, object]]:
    return [dict(row) for row in rows]


async def prepare_database(admin_dsn: str, database: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(admin_dsn)
    try:
        existing = await connection.fetchval(
            "SELECT count(*) FROM pg_roles WHERE rolname = ANY($1::text[])",
            list(_RUNTIME_ROLES),
        )
        if existing:
            raise RuntimeError("Historical upgrade target already contains runtime roles.")
        await connection.execute(f"CREATE DATABASE {quote_identifier(database)}")
    finally:
        await connection.close()


async def cleanup_database(admin_dsn: str, database: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(admin_dsn)
    try:
        await connection.execute(
            f"DROP DATABASE IF EXISTS {quote_identifier(database)} WITH (FORCE)"
        )
        for role in reversed(_RUNTIME_ROLES):
            await connection.execute(f"DROP ROLE IF EXISTS {quote_identifier(role)}")
    finally:
        await connection.close()


async def seed_historical_database(database_dsn: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(database_dsn)
    try:
        await connection.execute(
            """
            INSERT INTO fastapi_effects.events
                (tenant_id,event_id,event_type,event_version,canonical_version,payload,
                 payload_canonical,payload_sha256,principal,occurred_at,created_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '20000000-0000-0000-0000-000000000001','upgrade.probe',1,1,'{}'::jsonb,
                 convert_to('fastapi_effects:canonical-json:v1\n{}','UTF8'),
                 decode(repeat('00',32),'hex'),
                 '{"tenant_id":"10000000-0000-0000-0000-000000000001","subject_id":"upgrade-probe","scopes":[]}'::jsonb,
                 '2026-09-20T21:58:29Z','2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.deliveries
                (tenant_id,delivery_id,event_id,route_key,route_version,destination_kind,
                 destination_key,route_snapshot,route_snapshot_bytes,state,attempts_started,
                 next_attempt_at,created_at,updated_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '30000000-0000-0000-0000-000000000001',
                 '20000000-0000-0000-0000-000000000001','upgrade.probe',1,'handler',
                 'upgrade-probe','{}'::jsonb,convert_to('{}','UTF8'),'succeeded',1,
                 '2026-09-20T21:58:29Z','2026-09-20T21:58:29Z','2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.attempts
                (tenant_id,attempt_id,delivery_id,attempt_number,lease_token,outcome,
                 started_at,finished_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '40000000-0000-0000-0000-000000000001',
                 '30000000-0000-0000-0000-000000000001',1,
                 '50000000-0000-0000-0000-000000000001','succeeded',
                 '2026-09-20T21:58:29Z','2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.webhook_secret_sets
                (tenant_id,secret_set_id,revision,created_by,created_at,updated_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '60000000-0000-0000-0000-000000000001',1,'upgrade-probe',
                 '2026-09-20T21:58:29Z','2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.webhook_subscriptions
                (tenant_id,subscription_id,current_version,revision,state,failure_streak,
                 auto_pause_threshold,created_by,updated_by,created_at,updated_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '70000000-0000-0000-0000-000000000001',1,1,'active',0,20,
                 'upgrade-probe','upgrade-probe','2026-09-20T21:58:29Z',
                 '2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.webhook_secret_versions
                (tenant_id,secret_set_id,secret_version,key_id,nonce,ciphertext,state,created_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '60000000-0000-0000-0000-000000000001',1,'upgrade-key',
                 decode(repeat('00',12),'hex'),decode(repeat('00',16),'hex'),'active',
                 '2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.webhook_subscription_versions
                (tenant_id,subscription_id,version,exact_event_types,endpoint_url,retry_policy,
                 secret_set_id,created_by,created_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '70000000-0000-0000-0000-000000000001',1,'["upgrade.probe"]'::jsonb,
                 'https://example.test/upgrade','{}'::jsonb,
                 '60000000-0000-0000-0000-000000000001','upgrade-probe',
                 '2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.webhook_audit
                (tenant_id,audit_id,subject_id,action,target_kind,target_id,details,occurred_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '80000000-0000-0000-0000-000000000001','upgrade-probe','created',
                 'subscription','70000000-0000-0000-0000-000000000001','{}'::jsonb,
                 '2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.taskiq_handoffs
                (tenant_id,handoff_id,delivery_id,attempt_id,task_id,handoff_token,state,
                 principal,route_snapshot,route_snapshot_bytes,event_metadata,execution_count,
                 prepared_at,enqueued_at,finished_at,updated_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 '90000000-0000-0000-0000-000000000001',
                 '30000000-0000-0000-0000-000000000001',
                 '40000000-0000-0000-0000-000000000001','upgrade-task',
                 'a0000000-0000-0000-0000-000000000001','succeeded','{}'::jsonb,
                 '{}'::jsonb,convert_to('{}','UTF8'),'{}'::jsonb,1,
                 '2026-09-20T21:58:29Z','2026-09-20T21:58:29Z',
                 '2026-09-20T21:58:29Z','2026-09-20T21:58:29Z');

            INSERT INTO fastapi_effects.commands
                (tenant_id,command_id,route_id,method,key_digest,generation,is_current,
                 subject_id,fingerprint_version,fingerprint,state,response_status,
                 response_headers,response_body,response_media_type,created_at,updated_at,
                 expires_at,completed_at)
            VALUES
                ('10000000-0000-0000-0000-000000000001',
                 'b0000000-0000-0000-0000-000000000001','upgrade.probe','POST',
                 decode(repeat('00',32),'hex'),1,true,'upgrade-probe',1,
                 decode(repeat('00',32),'hex'),'completed',200,'{}'::jsonb,
                 convert_to('{}','UTF8'),'application/json','2026-09-20T21:58:29Z',
                 '2026-09-20T21:58:29Z','2099-01-01T00:00:00Z','2026-09-20T21:58:29Z');
            """
        )
    finally:
        await connection.close()


async def contract_snapshot(database_dsn: str) -> dict[str, object]:
    import asyncpg

    connection = await asyncpg.connect(database_dsn)
    try:
        server_version = str(await connection.fetchval("SHOW server_version"))
        roles = records(
            await connection.fetch(
                """
                SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin,
                       rolinherit, rolbypassrls
                FROM pg_roles WHERE rolname = ANY($1::text[]) ORDER BY rolname
                """,
                list(_RUNTIME_ROLES),
            )
        )
        schemas = records(
            await connection.fetch(
                """
                SELECT n.nspname AS schema_name, pg_get_userbyid(n.nspowner) AS owner,
                       COALESCE(n.nspacl::text, '') AS acl
                FROM pg_namespace n WHERE n.nspname = 'fastapi_effects'
                """
            )
        )
        relations = records(
            await connection.fetch(
                """
                SELECT c.relname AS table_name, pg_get_userbyid(c.relowner) AS owner,
                       c.relrowsecurity AS rls, c.relforcerowsecurity AS force_rls
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'fastapi_effects' AND c.relkind IN ('r','p')
                ORDER BY c.relname
                """
            )
        )
        constraints = records(
            await connection.fetch(
                """
                SELECT c.relname AS table_name, con.conname AS constraint_name,
                       con.contype::text AS constraint_type,
                       pg_get_constraintdef(con.oid, true) AS definition
                FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'fastapi_effects'
                ORDER BY c.relname, con.conname
                """
            )
        )
        indexes = records(
            await connection.fetch(
                """
                SELECT t.relname AS table_name, i.relname AS index_name,
                       pg_get_indexdef(i.oid) AS definition
                FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
                JOIN pg_class t ON t.oid = x.indrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'fastapi_effects'
                ORDER BY t.relname, i.relname
                """
            )
        )
        policies = records(
            await connection.fetch(
                """
                SELECT tablename AS table_name, policyname AS policy_name, permissive,
                       array_to_string(roles, ',') AS roles, cmd,
                       COALESCE(qual, '') AS using_expression,
                       COALESCE(with_check, '') AS check_expression
                FROM pg_policies WHERE schemaname = 'fastapi_effects'
                ORDER BY tablename, policyname
                """
            )
        )
        table_grants = records(
            await connection.fetch(
                """
                SELECT c.relname AS table_name,
                       CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
                            ELSE pg_get_userbyid(acl.grantee) END AS grantee,
                       acl.privilege_type, acl.is_grantable
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                CROSS JOIN LATERAL aclexplode(
                    COALESCE(c.relacl, acldefault('r', c.relowner))
                ) AS acl
                WHERE n.nspname = 'fastapi_effects' AND c.relkind IN ('r','p')
                ORDER BY c.relname, grantee, acl.privilege_type
                """
            )
        )
        functions = records(
            await connection.fetch(
                """
                SELECT p.proname AS function_name,
                       pg_get_function_identity_arguments(p.oid) AS arguments,
                       pg_get_userbyid(p.proowner) AS owner, p.prosecdef AS security_definer,
                       COALESCE(array_to_string(p.proconfig, ','), '') AS configuration,
                       COALESCE(p.proacl::text, '') AS acl
                FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'fastapi_effects'
                ORDER BY p.proname, arguments
                """
            )
        )
        triggers = records(
            await connection.fetch(
                """
                SELECT c.relname AS table_name, t.tgname AS trigger_name,
                       pg_get_triggerdef(t.oid, true) AS definition
                FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'fastapi_effects' AND NOT t.tgisinternal
                ORDER BY c.relname, t.tgname
                """
            )
        )
        revisions = {
            str(row["component"]): int(row["revision"])
            for row in await connection.fetch(
                "SELECT component, revision FROM fastapi_effects.schema_revision ORDER BY component"
            )
        }
        alembic_versions = [
            str(row["version_num"])
            for row in await connection.fetch(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            )
        ]
        counts = {
            table: int(await connection.fetchval(f"SELECT count(*) FROM fastapi_effects.{table}"))
            for table in _SEEDED_TABLES
        }
    finally:
        await connection.close()
    return {
        "server_version": server_version,
        "roles": roles,
        "schemas": schemas,
        "relations": relations,
        "constraints": constraints,
        "indexes": indexes,
        "policies": policies,
        "table_grants": table_grants,
        "functions": functions,
        "triggers": triggers,
        "revision_markers": revisions,
        "alembic_versions": alembic_versions,
        "seed_counts": counts,
    }


def rows_for_tables(snapshot: Mapping[str, object], key: str, tables: set[str]) -> object:
    value = snapshot[key]
    if not isinstance(value, list):
        raise AssertionError(f"Snapshot {key} is not a list.")
    return [row for row in value if isinstance(row, dict) and row.get("table_name") in tables]


def assert_upgrade_contract(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> None:
    if before.get("revision_markers") != _BASELINE_REVISIONS:
        raise AssertionError("The public wheel did not create its recorded revision markers.")
    if before.get("alembic_versions") != ["0005_webhook_retention"]:
        raise AssertionError("The public wheel did not install its recorded Alembic head.")
    if after.get("revision_markers") != dict(SCHEMA_REVISION_REGISTRY):
        raise AssertionError("Candidate component revision markers are not current.")
    if after.get("alembic_versions") != [MIGRATION_HEAD]:
        raise AssertionError("Candidate Alembic revision is not current.")
    expected_counts = dict.fromkeys(_SEEDED_TABLES, 1)
    if before.get("seed_counts") != expected_counts or after.get("seed_counts") != expected_counts:
        raise AssertionError("Historical seeded data was not preserved.")
    if before.get("roles") != after.get("roles") or before.get("schemas") != after.get("schemas"):
        raise AssertionError("Runtime role or schema ownership changed during upgrade.")
    roles = after.get("roles")
    if not isinstance(roles, list) or {
        row.get("rolname") for row in roles if isinstance(row, dict)
    } != set(_RUNTIME_ROLES):
        raise AssertionError("Candidate runtime roles are incomplete.")
    for role in roles:
        assert isinstance(role, dict)
        if any(
            role.get(field) is not False
            for field in (
                "rolsuper",
                "rolcreaterole",
                "rolcreatedb",
                "rolcanlogin",
                "rolinherit",
                "rolbypassrls",
            )
        ):
            raise AssertionError("Candidate runtime role attributes are unsafe.")
    before_relations = before.get("relations")
    after_relations = after.get("relations")
    if not isinstance(before_relations, list) or not isinstance(after_relations, list):
        raise AssertionError("Relation ownership evidence is missing.")
    baseline_tables = {
        str(row["table_name"])
        for row in before_relations
        if isinstance(row, dict) and isinstance(row.get("table_name"), str)
    }
    if rows_for_tables(after, "relations", baseline_tables) != before_relations:
        raise AssertionError("Published table ownership or RLS flags changed unexpectedly.")
    for row in after_relations:
        assert isinstance(row, dict)
        if row.get("owner") != "fastapi_effects_migration":
            raise AssertionError("Candidate table is not owned by the migration role.")
        if row.get("table_name") != "schema_revision" and (
            row.get("rls") is not True or row.get("force_rls") is not True
        ):
            raise AssertionError("Candidate tenant table does not force row-level security.")
    for key in ("constraints", "indexes", "policies", "table_grants", "triggers"):
        if rows_for_tables(before, key, baseline_tables) != rows_for_tables(
            after, key, baseline_tables
        ):
            raise AssertionError(f"Published {key} changed unexpectedly during upgrade.")
    before_functions = before.get("functions")
    after_functions = after.get("functions")
    if not isinstance(before_functions, list) or not isinstance(after_functions, list):
        raise AssertionError("Function security evidence is missing.")
    baseline_functions = {
        (row.get("function_name"), row.get("arguments"))
        for row in before_functions
        if isinstance(row, dict)
    }
    retained_functions = [
        row
        for row in after_functions
        if isinstance(row, dict)
        and (row.get("function_name"), row.get("arguments")) in baseline_functions
    ]
    if retained_functions != before_functions:
        raise AssertionError("Published function ownership or privileges changed unexpectedly.")
    after_grants = after.get("table_grants")
    if not isinstance(after_grants, list):
        raise AssertionError("Table grant evidence is missing.")
    if any(row.get("grantee") == "PUBLIC" for row in after_grants if isinstance(row, dict)):
        raise AssertionError("Candidate tables grant privileges to PUBLIC.")
    if not before.get("constraints") or not before.get("indexes"):
        raise AssertionError("Historical constraint or index evidence is empty.")


def artifact_command(
    python: Path,
    database_dsn: str,
    *arguments: str,
    cwd: Path,
) -> None:
    environment = clean_environment()
    environment["FASTAPI_EFFECTS_DATABASE_DSN"] = database_dsn
    run(str(python), "-m", "fastapi_effects", *arguments, cwd=cwd, environment=environment)


async def verify_target(
    label: str,
    admin_dsn: str,
    *,
    historical_python: Path,
    candidate_python: Path,
    cwd: Path,
) -> dict[str, object]:
    expected_major = int(label.removeprefix("postgresql-"))
    database = f"fastapi_effects_upgrade_{expected_major}_{uuid4().hex[:10]}"
    await prepare_database(admin_dsn, database)
    plain_dsn = dsn_for_database(admin_dsn, database)
    migration_dsn = dsn_for_database(admin_dsn, database, sqlalchemy=True)
    try:
        artifact_command(historical_python, migration_dsn, "schema", "upgrade", cwd=cwd)
        await seed_historical_database(plain_dsn)
        before = await contract_snapshot(plain_dsn)
        actual_major = int(str(before["server_version"]).split(".", 1)[0])
        if actual_major != expected_major:
            raise AssertionError(
                f"Upgrade target {label} resolved PostgreSQL {before['server_version']}."
            )
        artifact_command(candidate_python, migration_dsn, "schema", "upgrade", cwd=cwd)
        after = await contract_snapshot(plain_dsn)
        assert_upgrade_contract(before, after)
        return {
            "target": label,
            "postgresql_major": actual_major,
            "server_version": after["server_version"],
            "status": "passed",
            "checks": list(_CHECKS),
            "historical_contract_sha256": canonical_sha256(before),
            "candidate_contract_sha256": canonical_sha256(after),
            "seed_counts": after["seed_counts"],
            "revision_markers": after["revision_markers"],
            "alembic_versions": after["alembic_versions"],
        }
    finally:
        await cleanup_database(admin_dsn, database)


def parse_targets(values: Sequence[str]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for value in values:
        label, separator, dsn = value.partition("=")
        if not separator or label not in {"postgresql-16", "postgresql-18"} or not dsn:
            raise ValueError("Targets must be postgresql-16=<dsn> or postgresql-18=<dsn>.")
        targets.append((label, dsn))
    if {label for label, _ in targets} != {"postgresql-16", "postgresql-18"} or len(targets) != 2:
        raise ValueError("Historical upgrade evidence requires exactly PostgreSQL 16 and 18.")
    return sorted(targets)


async def async_main(args: argparse.Namespace) -> int:
    inventory = args.inventory.resolve()
    candidate_wheel = args.candidate_wheel.resolve()
    constraints = args.constraints.resolve()
    output = args.output.resolve()
    if not inventory.is_file() or not candidate_wheel.is_file() or not constraints.is_file():
        raise ValueError("Inventory, candidate wheel, and constraints must exist.")
    if not candidate_wheel.name.endswith(".whl"):
        raise ValueError("Historical upgrade requires the exact candidate wheel.")
    historical = load_historical_wheel(inventory)
    targets = parse_targets(args.target)
    with tempfile.TemporaryDirectory(prefix="fastapi_effects_published_upgrade-") as raw:
        work = Path(raw)
        historical_wheel = work / str(historical["filename"])
        download_historical_wheel(historical, historical_wheel)
        historical_python = create_artifact_environment(
            work / "historical-venv",
            historical_wheel,
            constraints=constraints,
            cwd=work,
        )
        candidate_python = create_artifact_environment(
            work / "candidate-venv",
            candidate_wheel,
            constraints=constraints,
            cwd=work,
        )
        results = [
            await verify_target(
                label,
                dsn,
                historical_python=historical_python,
                candidate_python=candidate_python,
                cwd=work,
            )
            for label, dsn in targets
        ]
    report = {
        "schema_version": 1,
        "status": "passed",
        "historical": historical,
        "candidate": {
            "filename": candidate_wheel.name,
            "sha256": sha256_file(candidate_wheel),
        },
        "targets": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Published-artifact upgrade evidence written to {output.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--candidate-wheel", type=Path, required=True)
    parser.add_argument("--constraints", type=Path, required=True)
    parser.add_argument("--target", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

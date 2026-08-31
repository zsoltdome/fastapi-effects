from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi_mergen.postgres.migrations import frozen_v1

REVISIONS = Path(__file__).resolve().parents[2] / "src/fastapi_mergen/postgres/migrations/versions"
FORBIDDEN_MUTABLE_MODULES = {
    "fastapi_mergen.executors.taskiq.models",
    "fastapi_mergen.idempotency.models",
    "fastapi_mergen.postgres.command_schema",
    "fastapi_mergen.postgres.executor_schema",
    "fastapi_mergen.postgres.rls",
    "fastapi_mergen.postgres.roles",
    "fastapi_mergen.postgres.webhook_schema",
    "fastapi_mergen.sqlalchemy.models",
    "fastapi_mergen.webhooks.models",
}


def test_published_revisions_do_not_import_mutable_runtime_definitions() -> None:
    violations: list[str] = []
    for path in sorted(REVISIONS.glob("000*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN_MUTABLE_MODULES:
                violations.append(f"{path.name}: {node.module}")
    assert violations == []


def test_published_revision_contract_digest_is_frozen() -> None:
    config = SimpleNamespace(
        attributes={
            "runtime_roles": SimpleNamespace(
                migration="migration_probe",
                application="application_probe",
                relay="relay_probe",
            )
        }
    )
    roles = frozen_v1.role_names_v1(config)
    statements = [
        *frozen_v1.CORE_DDL_V1,
        *frozen_v1.WEBHOOK_DDL_V1,
        *frozen_v1.TASKIQ_DDL_V1,
        *frozen_v1.COMMAND_DDL_V1,
        *frozen_v1.core_rls_sql_v1(roles),
        *frozen_v1.webhook_rls_sql_v1(roles),
        *frozen_v1.webhook_grant_sql_v1(roles),
        *frozen_v1.executor_schema_sql_v1(roles),
        *frozen_v1.command_trigger_sql_v1(),
        *frozen_v1.command_schema_sql_v1(roles),
        *frozen_v1.webhook_retention_sql_v1(roles),
    ]
    encoded = json.dumps(statements, ensure_ascii=True, separators=(",", ":")).encode()

    assert hashlib.sha256(encoded).hexdigest() == (
        "45b06b41d1adba46eda13080ad441cfed2d67272264b730a86df6e07a355ba94"
    )

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scripts.verify_published_upgrade import (
    _BASELINE_REVISIONS,
    _RUNTIME_ROLES,
    _SEEDED_TABLES,
    ROOT,
    _display_path,
    assert_upgrade_contract,
    load_historical_wheel,
    parse_targets,
)


def _snapshot() -> dict[str, object]:
    roles = [
        {
            "rolname": role,
            "rolsuper": False,
            "rolcreaterole": False,
            "rolcreatedb": False,
            "rolcanlogin": False,
            "rolinherit": False,
            "rolbypassrls": False,
        }
        for role in sorted(_RUNTIME_ROLES)
    ]
    relations = [
        {
            "table_name": "events",
            "owner": "fastapi_effects_migration",
            "rls": True,
            "force_rls": True,
        },
        {
            "table_name": "schema_revision",
            "owner": "fastapi_effects_migration",
            "rls": False,
            "force_rls": False,
        },
    ]
    return {
        "server_version": "18.1",
        "roles": roles,
        "schemas": [
            {
                "schema_name": "fastapi_effects",
                "owner": "fastapi_effects_migration",
                "acl": "",
            }
        ],
        "relations": relations,
        "constraints": [
            {
                "table_name": "events",
                "constraint_name": "pk_events",
                "constraint_type": "p",
                "definition": "PRIMARY KEY (tenant_id, event_id)",
            }
        ],
        "indexes": [
            {
                "table_name": "events",
                "index_name": "pk_events",
                "definition": "CREATE UNIQUE INDEX pk_events",
            }
        ],
        "policies": [
            {
                "table_name": "events",
                "policy_name": "events_tenant",
                "permissive": "PERMISSIVE",
                "roles": "fastapi_effects_app",
                "cmd": "ALL",
                "using_expression": "true",
                "check_expression": "true",
            }
        ],
        "table_grants": [
            {
                "table_name": "events",
                "grantee": "fastapi_effects_app",
                "privilege_type": "SELECT",
                "is_grantable": False,
            }
        ],
        "functions": [
            {
                "function_name": "prune_webhook_history",
                "arguments": "uuid, timestamp with time zone, integer",
                "owner": "fastapi_effects_migration",
                "security_definer": True,
                "configuration": "search_path=pg_catalog, fastapi_effects",
                "acl": "",
            }
        ],
        "triggers": [
            {
                "table_name": "events",
                "trigger_name": "probe",
                "definition": "CREATE TRIGGER probe",
            }
        ],
        "revision_markers": dict(_BASELINE_REVISIONS),
        "alembic_versions": ["0005_webhook_retention"],
        "seed_counts": dict.fromkeys(_SEEDED_TABLES, 1),
    }


def test_release_inventory_selects_the_exact_public_wheel(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "version": "0.11.0a1",
                "artifacts": [
                    {
                        "kind": "wheel",
                        "filename": "fastapi_effects-0.11.0a1-py3-none-any.whl",
                        "url": "https://files.pythonhosted.org/packages/example.whl",
                        "sha256": "a" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    selected = load_historical_wheel(inventory)

    assert selected["version"] == "0.11.0a1"
    assert selected["sha256"] == "a" * 64


@pytest.mark.parametrize(
    ("url", "digest"),
    [
        ("http://files.pythonhosted.org/example.whl", "a" * 64),
        ("https://example.invalid/example.whl", "a" * 64),
        ("https://files.pythonhosted.org/example.whl", "not-a-digest"),
    ],
)
def test_release_inventory_rejects_unsafe_wheel_identity(
    tmp_path: Path,
    url: str,
    digest: str,
) -> None:
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "version": "0.11.0a1",
                "artifacts": [
                    {
                        "kind": "wheel",
                        "filename": "fastapi_effects-0.11.0a1-py3-none-any.whl",
                        "url": url,
                        "sha256": digest,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsafe"):
        load_historical_wheel(inventory)


def test_upgrade_contract_accepts_preserved_security_and_data() -> None:
    before = _snapshot()
    after = copy.deepcopy(before)

    assert_upgrade_contract(before, after)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("data", "seeded data"),
        ("grant", "table_grants"),
        ("rls", "RLS flags"),
        ("role", "Runtime role"),
        ("revision", "revision markers"),
    ],
)
def test_upgrade_contract_rejects_boundary_regressions(
    mutation: str,
    message: str,
) -> None:
    before = _snapshot()
    after = copy.deepcopy(before)
    if mutation == "data":
        after["seed_counts"]["events"] = 0  # type: ignore[index]
    elif mutation == "grant":
        after["table_grants"] = []
    elif mutation == "rls":
        after["relations"][0]["force_rls"] = False  # type: ignore[index]
    elif mutation == "role":
        after["roles"][0]["rolcanlogin"] = True  # type: ignore[index]
    else:
        after["revision_markers"] = {"core": 999}

    with pytest.raises(AssertionError, match=message):
        assert_upgrade_contract(before, after)


def test_upgrade_targets_require_both_supported_postgresql_lines() -> None:
    targets = parse_targets(
        [
            "postgresql-18=postgresql://postgres@localhost/postgres",
            "postgresql-16=postgresql://postgres@localhost/postgres",
        ]
    )

    assert [label for label, _ in targets] == ["postgresql-16", "postgresql-18"]

    with pytest.raises(ValueError, match="exactly PostgreSQL 16 and 18"):
        parse_targets(["postgresql-18=postgresql://postgres@localhost/postgres"])


def test_report_display_path_accepts_repository_and_external_destinations(
    tmp_path: Path,
) -> None:
    repository_report = ROOT / "build" / "release" / "upgrade.json"
    external_report = tmp_path / "upgrade.json"

    assert _display_path(repository_report) == Path("build/release/upgrade.json")
    assert _display_path(external_report) == external_report

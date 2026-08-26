#!/usr/bin/env python3
"""Audit local M13 implementation without pretending external gates are complete."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import fastapi_mergen
from fastapi_mergen.postgres.revisions import MIGRATION_HEAD, SCHEMA_REVISION_REGISTRY

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "docs/reference/public-api.md",
    "docs/compatibility.md",
    "docs/operations/migrations.md",
    "docs/operations/performance.md",
    "docs/operations/failure-recovery.md",
    "docs/operations/observability.md",
    "docs/operations/backup-restore.md",
    "docs/operations/retention.md",
    "docs/evidence/compatibility-local.json",
    "docs/evidence/postgres-restart-16.json",
    "docs/evidence/postgres-restart-18.json",
    "docs/tutorials/quickstart.md",
    "docs/planning/design-partner-protocol.md",
    "docs/planning/production-readiness-record.json",
    "docs/planning/known-limitations.md",
    "docs/security-review/findings.md",
    "docs/release-notes/1.0.0rc1.md",
    "docs/release-notes/1.0.0.md",
    "benchmarks/thresholds.json",
    "benchmarks/results/local-pg16.json",
    "benchmarks/results/local-pg18.json",
    "tests/chaos/scenarios.json",
    ".github/workflows/compatibility.yml",
    ".github/workflows/benchmarks.yml",
    ".github/workflows/release.yml",
    ".github/workflows/publish.yml",
    "scripts/benchmark.py",
    "scripts/chaos_harness.py",
    "scripts/generate_sbom.py",
    "scripts/generate_real_certification.py",
    "scripts/verify_hosted_release_checks.py",
    "scripts/write_compatibility_evidence.py",
    "scripts/rehearse_postgres_restart.py",
    "scripts/verify_restore.py",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-external", action="store_true")
    args = parser.parse_args()
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        raise AssertionError(f"M13 required files missing: {missing}")
    release_workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    publish_workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    compatibility_workflow = (ROOT / ".github/workflows/compatibility.yml").read_text(
        encoding="utf-8"
    )
    for name, content, required_tokens in (
        (
            "release",
            release_workflow,
            (
                "generate_real_certification.py",
                "verify_hosted_release_checks.py",
                "pytest -q -m integration",
                "pip-audit",
            ),
        ),
        (
            "publish",
            publish_workflow,
            (
                "generate_real_certification.py",
                "verify_hosted_release_checks.py",
                "audit_release_candidate.py",
                "pip-audit",
            ),
        ),
        (
            "compatibility",
            compatibility_workflow,
            ("write_compatibility_evidence.py", "MERGEN_TEST_REDIS_URL"),
        ),
    ):
        absent = [token for token in required_tokens if token not in content]
        if absent:
            raise AssertionError(f"M13 {name} workflow omits mandatory gates: {absent}")
    if MIGRATION_HEAD != "0005_webhook_retention" or dict(SCHEMA_REVISION_REGISTRY) != {
        "core": 1,
        "webhooks": 2,
        "executor.taskiq": 1,
        "commands": 1,
    }:
        raise AssertionError("M13 schema registry differs from the reviewed head")
    api_document = (ROOT / "docs/reference/public-api.md").read_text(encoding="utf-8")
    undocumented = [name for name in fastapi_mergen.__all__ if name not in api_document]
    if undocumented:
        raise AssertionError(f"M13 public root exports are undocumented: {undocumented}")
    for version in ("16", "18"):
        result = json.loads(
            (ROOT / f"benchmarks/results/local-pg{version}.json").read_text(encoding="utf-8")
        )
        if not all(result["correctness"].values()):
            raise AssertionError(f"PostgreSQL {version} benchmark correctness failed")
        restart = json.loads(
            (ROOT / f"docs/evidence/postgres-restart-{version}.json").read_text(encoding="utf-8")
        )
        if not (
            restart["result"] == "pass"
            and restart["expected_major"] == int(version)
            and restart["restart_observed"]
            and restart["schema_compatible"]
            and restart["doctor_healthy"]
            and restart["event_identity_preserved"]
            and restart["delivery_identity_preserved"]
        ):
            raise AssertionError(f"PostgreSQL {version} restart rehearsal failed")
    declared_compatibility = json.loads(
        (ROOT / "tests/compatibility/evidence.json").read_text(encoding="utf-8")
    )
    compatibility = json.loads(
        (ROOT / "docs/evidence/compatibility-local.json").read_text(encoding="utf-8")
    )
    if (
        compatibility.get("evidence_kind") != "historical-local-snapshot"
        or compatibility.get("release_authority") is not False
        or len(compatibility.get("binding", {}).get("implementation_commit", "")) != 40
        or len(compatibility.get("binding", {}).get("lock_sha256", "")) != 64
        or not declared_compatibility["evidence_ids"]
    ):
        raise AssertionError("M13 historical compatibility snapshot is not safely bound")
    readiness = json.loads(
        (ROOT / "docs/planning/production-readiness-record.json").read_text(encoding="utf-8")
    )
    externally_blocked = (
        len(readiness.get("partners", [])) < 2
        or readiness.get("independent_security_review", {}).get("status") != "complete"
        or readiness.get("rc_observation", {}).get("status") != "complete"
        or readiness.get("approval", {}).get("decision") != "go"
    )
    if not externally_blocked:
        raise AssertionError("Pre-RC repository unexpectedly reports external approval")
    if args.require_external:
        raise AssertionError(
            "External design-partner, independent-review, and RC observation gates are incomplete"
        )
    print("Milestone 13 local hardening audit passed; external RC/v1 gates remain fail-closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

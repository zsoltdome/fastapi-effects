#!/usr/bin/env python3
"""Audit the cumulative M8 core runtime and optionally its live PostgreSQL path."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi_mergen import __version__  # noqa: E402
from fastapi_mergen.conformance import CertificationProfile  # noqa: E402
from fastapi_mergen.sqlalchemy.models import (  # noqa: E402
    AttemptRow,
    DeliveryRow,
    EventRow,
    SchemaRevisionRow,
)

MINIMUM_RELEASE = (0, 7, 0)
REQUIRED_PATHS = (
    "src/fastapi_mergen/sqlalchemy/canonical.py",
    "src/fastapi_mergen/sqlalchemy/models.py",
    "src/fastapi_mergen/sqlalchemy/repository.py",
    "src/fastapi_mergen/sqlalchemy/uow.py",
    "src/fastapi_mergen/postgres/migrations/versions/0001_core_runtime.py",
    "src/fastapi_mergen/postgres/diagnostics.py",
    "src/fastapi_mergen/postgres/leasing.py",
    "src/fastapi_mergen/postgres/relay.py",
    "src/fastapi_mergen/handlers/executor.py",
    "src/fastapi_mergen/testing/postgres_driver.py",
    "tests/conformance/test_real_core_runtime.py",
    "tests/integration/test_core_migration.py",
    "tests/integration/test_invoicing_postgres_boot.py",
    "docs/adr/ADR-006-runtime-recovery.md",
    "docs/adr/ADR-010-leases-and-replay.md",
    "uv.lock",
)


def _static_audit() -> list[str]:
    evidence: list[str] = []
    match = re.match(r"^\d+\.\d+\.\d+", __version__)
    release = () if match is None else tuple(int(item) for item in match.group().split("."))
    if release < MINIMUM_RELEASE:
        raise AssertionError(f"version is {__version__}, expected M8 or later")
    evidence.append(f"version={__version__}")
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).is_file()]
    if missing:
        raise AssertionError(f"missing M8 paths: {missing}")
    evidence.append(f"required_paths={len(REQUIRED_PATHS)}")

    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    if project["name"] != "fastapi-mergen" or project["authors"] != [{"name": "mergen-institute"}]:
        raise AssertionError("distribution identity changed")
    if not any(str(item).startswith("asyncpg") for item in project["dependencies"]):
        raise AssertionError("asyncpg is not a runtime dependency")
    evidence.append("metadata=valid")

    mapped_tables: tuple[Any, ...] = (
        SchemaRevisionRow.__table__,
        EventRow.__table__,
        DeliveryRow.__table__,
        AttemptRow.__table__,
    )
    tables = {f"{table.schema}.{table.name}" for table in mapped_tables}
    expected_tables = {
        "fastapi_mergen.schema_revision",
        "fastapi_mergen.events",
        "fastapi_mergen.deliveries",
        "fastapi_mergen.attempts",
    }
    if tables != expected_tables:
        raise AssertionError(f"unexpected core table set: {sorted(tables)}")
    evidence.append("schema=core-v1")

    runtime_roots = ("postgres", "sqlalchemy", "handlers")
    offenders: list[str] = []
    for root in runtime_roots:
        for path in (SRC / "fastapi_mergen" / root).rglob("*.py"):
            if "raise MilestoneNotImplementedError" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))
    if offenders:
        raise AssertionError(f"advertised runtime stubs remain: {offenders}")
    evidence.append("reachable_stubs=none")

    if {
        CertificationProfile.CORE.value,
        CertificationProfile.DELIVERY.value,
        CertificationProfile.SECURITY.value,
    } - {profile.value for profile in CertificationProfile}:
        raise AssertionError("M8 conformance profiles are unavailable")
    evidence.append("profiles=core,delivery,security")
    return evidence


def _live_audit(dsn: str) -> None:
    environment = os.environ.copy()
    environment["MERGEN_TEST_ADMIN_DSN"] = dsn
    subprocess.run(
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/conformance/test_real_core_runtime.py",
            "tests/integration/test_core_migration.py",
            "tests/integration/test_doctor.py",
            "tests/integration/test_invoicing_postgres_boot.py",
        ),
        cwd=ROOT,
        env=environment,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres-dsn")
    args = parser.parse_args()
    evidence = _static_audit()
    if args.postgres_dsn:
        _live_audit(args.postgres_dsn)
        evidence.append("live_postgres=pass")
    print("Milestone 8 audit passed: " + "; ".join(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

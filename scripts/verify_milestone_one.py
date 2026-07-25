#!/usr/bin/env python3
"""Verify the frozen Milestone 1 repository and governance contract."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "fastapi_mergen"
AUTHOR_NAME = "mergen-institute"
AUTHOR_EMAIL = "mergen-institute@users.noreply.github.com"
ALLOWED_BRANCH_PREFIXES = {"build", "chore", "ci", "docs", "feat", "fix", "refactor", "test"}
FORBIDDEN_PACKAGE_NAMES = {
    "idempotency",
    "mcp",
    "queue",
    "queues",
    "tasks",
    "workflow",
    "workflows",
}
REQUIRED_PATHS = {
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "IMPLEMENTATION_REPORT.md",
    "compose.yaml",
    ".env.example",
    ".github/workflows/ci.yml",
    ".github/workflows/package.yml",
    ".github/workflows/security.yml",
    ".github/workflows/publish.yml",
    "src/fastapi_mergen/__init__.py",
    "src/fastapi_mergen/api.py",
    "src/fastapi_mergen/errors.py",
    "src/fastapi_mergen/py.typed",
    "src/fastapi_mergen/core/protocols.py",
    "src/fastapi_mergen/postgres/__init__.py",
    "src/fastapi_mergen/postgres/store.py",
    "src/fastapi_mergen/sqlalchemy/__init__.py",
    "src/fastapi_mergen/sqlalchemy/uow.py",
    "scripts/check.py",
    "scripts/architecture_gate.py",
    "scripts/build_and_test_artifacts.py",
    "scripts/wait_for_postgres.py",
    "docs/concepts/boundary-contract.md",
    "docs/concepts/guarantees.md",
    "docs/concepts/threat-model.md",
    "docs/concepts/authorization.md",
    "docs/adr/0001-trust-model.md",
    "docs/adr/0002-explicit-uow-transaction.md",
    "docs/adr/0003-event-delivery-attempt-model.md",
    "docs/adr/0004-routing-and-policy-snapshots.md",
    "docs/adr/0005-relay-state-machine.md",
    "docs/reference/data-model.md",
    "docs/reference/route-snapshot-schema.md",
    "docs/reference/failure-taxonomy.md",
    "docs/reference/uow-lifecycle.md",
    "docs/reference/conformance-map.md",
    "docs/operations/roles-and-rls.md",
    "docs/operations/relay.md",
    "docs/operations/retries-and-replay.md",
    "docs/milestone-1-review.md",
    "examples/invoicing/app/main.py",
    "examples/invoicing/app/models.py",
    "examples/invoicing/app/schemas.py",
    "examples/invoicing/app/auth.py",
    "examples/invoicing/app/mergen_config.py",
    "examples/invoicing/tests/test_boot.py",
    "tests/integration/postgres.py",
    "tests/integration/test_postgres_environment.py",
    "tests/integration/test_invoicing_postgres_boot.py",
    "tests/packaging/test_clean_install.py",
    "tests/packaging/test_metadata.py",
    "tests/packaging/test_optional_imports.py",
}
REQUIRED_ROOT_EXPORTS = {
    "AuthorizationDenied",
    "AuthorizationExpired",
    "AuthorizationMode",
    "DedupeConflict",
    "EffectContext",
    "Event",
    "LeaseLost",
    "Mergen",
    "MergenConfigurationError",
    "MergenError",
    "MergenUnitOfWork",
    "MilestoneNotImplementedError",
    "PermanentDeliveryError",
    "Principal",
    "RetryPolicy",
    "RetryableDeliveryError",
    "SchemaRevisionMismatch",
    "__version__",
}


def fail(message: str) -> None:
    raise AssertionError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.rstrip()


def check_required_paths() -> None:
    missing = sorted(path for path in REQUIRED_PATHS if not (ROOT / path).is_file())
    if missing:
        fail(f"required Milestone 1 files are missing: {missing}")


def check_metadata() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        data: dict[str, Any] = tomllib.load(stream)
    project = data["project"]
    if project["name"] != "fastapi-mergen":
        fail("distribution name must be fastapi-mergen")
    if project["requires-python"] != ">=3.11,<3.15":
        fail("supported Python range must remain 3.11 through 3.14")
    if project.get("authors") != [{"name": AUTHOR_NAME}]:
        fail("project metadata must name only mergen-institute")
    scripts = project.get("scripts", {})
    if scripts.get("fastapi-mergen") != "fastapi_mergen.cli.main:main":
        fail("console entry point must be fastapi-mergen")
    extras = project.get("optional-dependencies", {})
    if set(extras) != {"otel", "webhooks"}:
        fail("only webhooks and otel optional extras are permitted in Milestone 1")
    base_dependencies = "\n".join(project.get("dependencies", [])).lower()
    for optional in ("cryptography", "httpx", "opentelemetry", "standardwebhooks"):
        if optional in base_dependencies:
            fail(f"optional dependency leaked into base dependencies: {optional}")
    package_data = data["tool"]["setuptools"]["package-data"]
    if "py.typed" not in package_data.get("fastapi_mergen", []):
        fail("typed-package marker is not configured for the wheel")


def literal_all(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        has_all = any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        )
        if not has_all:
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            fail(f"{path.relative_to(ROOT)} __all__ must be a literal sequence")
        exports = {
            element.value
            for element in node.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
        return exports
    fail(f"{path.relative_to(ROOT)} does not define __all__")
    return set()


def check_public_surface() -> None:
    if literal_all(PACKAGE / "__init__.py") != REQUIRED_ROOT_EXPORTS:
        fail("root package exports differ from the frozen public API")
    if (ROOT / "src" / "mergen").exists():
        fail("occupied top-level mergen import package exists")
    package_directories = {
        path.name for path in PACKAGE.iterdir() if path.is_dir() and not path.name.startswith("__")
    }
    forbidden = sorted(package_directories & FORBIDDEN_PACKAGE_NAMES)
    if forbidden:
        fail(f"out-of-scope package directories exist: {forbidden}")


def require_phrases(path: str, phrases: tuple[str, ...]) -> None:
    text = re.sub(r"\s+", " ", read(path).lower())
    missing = [
        phrase
        for phrase in phrases
        if re.sub(r"\s+", " ", phrase.lower()) not in text
    ]
    if missing:
        fail(f"{path} is missing required contract language: {missing}")


def check_contract_documents() -> None:
    require_phrases(
        "docs/concepts/boundary-contract.md",
        (
            "BC-01 — Atomic intent",
            "BC-02 — Tenant continuity",
            "BC-03 — Explicit authority provenance",
            "BC-04 — Stable retry identity",
            "BC-05 — Independent fan-out",
            "BC-06 — Causal lineage",
            "BC-07 — Replay accountability",
            "delivery is at least once",
            "ordering and cancellation are undefined and unsupported",
        ),
    )
    require_phrases(
        "docs/concepts/guarantees.md",
        (
            "Atomic local commit",
            "At least once",
            "Effectively once only with durable consumer deduplication",
            "Same delivery/message ID; new attempt ID",
            "New delivery/message ID linked to original",
        ),
    )
    require_phrases(
        "docs/concepts/threat-model.md",
        (
            "cross-tenant",
            "pool",
            "stale",
            "revocation",
            "SSRF",
            "secret",
            "replay",
            "residual risk",
        ),
    )
    require_phrases(
        "docs/adr/0002-explicit-uow-transaction.md",
        (
            "already active",
            "before application SQL",
            "Nested Mergen UoWs are rejected",
            "savepoints",
            "Commit failure",
            "Cancellation",
            "Dependency finalizer failure",
        ),
    )
    require_phrases(
        "docs/adr/0003-event-delivery-attempt-model.md",
        (
            "composite tenant-safe foreign key",
            "canonical payload hash",
            "manual replay creates a new delivery",
            "Retention",
        ),
    )
    require_phrases(
        "docs/adr/0004-routing-and-policy-snapshots.md",
        (
            "exact event-type routes",
            "freeze the registry",
            "snapshot:   effective = origin ∩ route allowance",
            "revalidate: effective = current ∩ origin ceiling ∩ route allowance",
            "no Python callable, raw credential, or plaintext secret",
        ),
    )
    require_phrases(
        "docs/adr/0005-relay-state-machine.md",
        (
            "FOR UPDATE SKIP LOCKED",
            "fresh lease token",
            "commit before I/O",
            "bounded, not strict ordering",
            "Kill-point matrix",
            "full-jitter",
        ),
    )
    conformance = read("docs/reference/conformance-map.md")
    for identifier in ("BC-01", "BC-02", "BC-03", "BC-04", "BC-05", "BC-06", "BC-07"):
        if identifier not in conformance:
            fail(f"conformance map is missing {identifier}")
    require_phrases(
        "docs/reference/public-api-spike.md",
        (
            "from fastapi_mergen.postgres import PostgresStore",
            "from fastapi_mergen.sqlalchemy import MergenUnitOfWork",
            "fail-closed Milestone 1 declaration",
        ),
    )
    require_phrases(
        "docs/milestone-1-review.md",
        (
            "implementation complete; external matrix certification pending first CI run",
            "No unverified external gate is represented as having passed locally",
            "Milestone 1 implementation is signed off",
        ),
    )


def check_ci_and_postgres_harness() -> None:
    workflows = "\n".join(
        read(path)
        for path in (
            ".github/workflows/ci.yml",
            ".github/workflows/package.yml",
            ".github/workflows/security.yml",
            ".github/workflows/publish.yml",
        )
    )
    if "--extra test" in workflows:
        fail("CI refers to a nonexistent test optional extra")
    if "--locked" in workflows and not (ROOT / "uv.lock").exists():
        fail("CI requires a missing uv.lock")
    require_phrases(
        ".github/workflows/ci.yml",
        (
            'python: ["3.11", "3.12", "3.13", "3.14"]',
            'postgres: "16"',
            'postgres: "18"',
            'uv sync --group dev',
            'uv sync --group test',
        ),
    )
    require_phrases(
        ".github/workflows/publish.yml",
        ("release:", "id-token: write", "pypa/gh-action-pypi-publish@"),
    )
    compose = read("compose.yaml")
    for phrase in ("postgres16:", "postgres18:", "profiles: [pg16]", "profiles: [pg18]", "tmpfs:"):
        if phrase not in compose:
            fail(f"compose.yaml is missing: {phrase}")
    helper = read("tests/integration/postgres.py")
    for phrase in (
        "mergen_owner_",
        "mergen_app_",
        "mergen_relay_",
        "mergen_bad_",
        "BYPASSRLS",
        "DROP DATABASE IF EXISTS",
    ):
        if phrase not in helper:
            fail(f"PostgreSQL test fixture is missing: {phrase}")


def check_example_boot() -> None:
    code = (
        "from examples.invoicing.app.main import app; "
        "schema = app.openapi(); "
        "assert '/invoices' in schema['paths']; "
        "assert '/health' in schema['paths']"
    )
    subprocess.run((sys.executable, "-c", code), cwd=ROOT, check=True)


def check_git_governance(*, require_clean: bool) -> None:
    if not (ROOT / ".git").is_dir():
        fail("Milestone ZIP must preserve the Git repository")
    if require_clean:
        dirty = run_git("status", "--porcelain")
        if dirty:
            fail("working tree must be clean for final milestone verification")

    refs = run_git("for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
    for branch in refs:
        if branch == "main":
            continue
        if "/" not in branch:
            fail(f"branch lacks a typed prefix: {branch}")
        prefix, slug = branch.split("/", 1)
        if prefix not in ALLOWED_BRANCH_PREFIXES:
            fail(f"unsupported branch prefix: {branch}")
        word_count = len([part for part in re.split(r"[-_/]+", slug) if part])
        if not 3 <= word_count <= 7:
            fail(f"branch name must contain 3–7 short words: {branch}")

    records = run_git(
        "log",
        "--branches",
        "--format=%an%x1f%ae%x1f%cn%x1f%ce%x1f%s",
    ).splitlines()
    if not records:
        fail("Git history is empty")
    for record in records:
        author, author_email, committer, committer_email, subject = record.split("\x1f")
        if (author, committer) != (AUTHOR_NAME, AUTHOR_NAME):
            fail(f"non-Mergen author or committer found: {subject}")
        if (author_email, committer_email) != (AUTHOR_EMAIL, AUTHOR_EMAIL):
            fail(f"unexpected author or committer email found: {subject}")
        words = subject.split()
        if not 3 <= len(words) <= 7:
            fail(f"commit subject must contain 3–7 words: {subject!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Fail when tracked or untracked working-tree changes exist.",
    )
    parser.add_argument(
        "--skip-git-governance",
        action="store_true",
        help="Skip local branch/author checks in detached or contributor CI checkouts.",
    )
    args = parser.parse_args()

    check_required_paths()
    check_metadata()
    check_public_surface()
    check_contract_documents()
    check_ci_and_postgres_harness()
    check_example_boot()
    if not args.skip_git_governance:
        check_git_governance(require_clean=args.require_clean)
    print("Milestone 1 structural verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

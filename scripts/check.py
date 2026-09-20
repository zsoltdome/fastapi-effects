#!/usr/bin/env python3
"""Run the deterministic local quality gate."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def require(command: str) -> None:
    if shutil.which(command) is None:
        raise SystemExit(
            f"Required command '{command}' is unavailable. Run "
            "'uv sync --locked --all-extras --all-groups' first."
        )


def built_distributions(directory: Path) -> tuple[Path, ...]:
    """Return only distribution formats produced by ``uv build``."""
    artifacts = (*directory.glob("*.whl"), *directory.glob("*.tar.gz"))
    return tuple(sorted(artifacts))


def main(*, skip_artifact_build: bool = False) -> int:
    required: tuple[str, ...] = ("uv", "ruff", "mypy", "pytest", "mkdocs")
    if not skip_artifact_build:
        required = (*required, "twine")
    for command in required:
        require(command)
    run("uv", "lock", "--check")
    quality_roots = ("src", "tests", "examples", "scripts")
    run("ruff", "format", "--check", *quality_roots)
    run("ruff", "check", *quality_roots)
    run("mypy")
    run(sys.executable, "scripts/architecture_gate.py")
    run(
        sys.executable,
        "scripts/verify_milestone_one.py",
        "--skip-git-governance",
    )
    run(
        sys.executable,
        "scripts/audit_milestone_seven.py",
        "--skip-git-governance",
    )
    run(sys.executable, "scripts/audit_milestone_eight.py")
    run(sys.executable, "scripts/audit_milestone_nine.py")
    run(sys.executable, "scripts/audit_milestone_ten.py")
    run(sys.executable, "scripts/audit_milestone_eleven.py")
    run(sys.executable, "scripts/audit_milestone_twelve.py")
    run(sys.executable, "scripts/audit_milestone_thirteen.py")
    run(sys.executable, "scripts/audit_release_candidate.py", "--phase", "auto")
    run(sys.executable, "scripts/check_documentation.py")
    run("mkdocs", "build", "--strict")
    run(
        "pytest",
        "-q",
        "-m",
        "not integration and not packaging",
        "--cov=fastapi_effects",
        "--cov-report=term-missing",
        "--durations=20",
    )
    if not skip_artifact_build:
        run(sys.executable, "scripts/build_and_test_artifacts.py")
        distributions = built_distributions(ROOT / "dist")
        if not distributions:
            raise SystemExit("Artifact build did not create wheel or sdist files.")
        run("twine", "check", *(str(path) for path in distributions))
    return 0


def cli() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-artifact-build", action="store_true")
    args = parser.parse_args()
    return main(skip_artifact_build=args.skip_artifact_build)


if __name__ == "__main__":
    raise SystemExit(cli())

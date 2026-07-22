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
            "'uv sync --all-extras --all-groups' first."
        )


def main() -> int:
    for command in ("ruff", "mypy", "pytest"):
        require(command)
    run("ruff", "format", "--check", ".")
    run("ruff", "check", ".")
    run("mypy")
    run(sys.executable, "scripts/architecture_gate.py")
    run(sys.executable, "scripts/verify_milestone_one.py")
    run(
        sys.executable,
        "scripts/audit_milestone_seven.py",
        "--skip-git-governance",
    )
    run("pytest", "-q", "-m", "not integration and not packaging")
    run(sys.executable, "scripts/build_and_test_artifacts.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

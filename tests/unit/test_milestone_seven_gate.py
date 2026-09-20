from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts import audit_milestone_seven

ROOT = Path(__file__).resolve().parents[2]


def test_milestone_seven_structural_gate() -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/audit_milestone_seven.py",
            "--skip-git-governance",
        ],
        cwd=ROOT,
        check=True,
    )


def test_git_governance_scopes_history_and_preserves_exact_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recovery = (
        "ba6659f1eb10dbc3d384669aedd261b7f8ff397d\x00"
        "zsoltdome\x00zsemed@gmail.com\x00"
        "mergen-institute\x00zsemed@gmail.com\x00.gitignore"
    )
    current = (
        "a" * 40
        + "\x00zsoltdome\x00zsoltdome@users.noreply.github.com"
        + "\x00zsoltdome\x00zsoltdome@users.noreply.github.com"
        + "\x00Harden delivery runtime boundaries"
    )
    historical = (
        "b" * 40
        + "\x00zsoltdome\x00mergen-institute@users.noreply.github.com"
        + "\x00mergen-institute\x00mergen-institute@users.noreply.github.com"
        + "\x00Document milestone seven assurance"
    )

    def run_git(*arguments: str) -> str:
        if arguments[:2] == ("log", "--branches"):
            return f"{current}\n{historical}\n{recovery}"
        if arguments[0] == "for-each-ref":
            return "main"
        if arguments[0] == "status":
            return ""
        raise AssertionError(f"Unexpected Git arguments: {arguments}")

    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(audit_milestone_seven, "run_git", run_git)
    monkeypatch.setattr(audit_milestone_seven.subprocess, "run", run)

    result = audit_milestone_seven.check_git_governance()

    assert "governed identities" in result

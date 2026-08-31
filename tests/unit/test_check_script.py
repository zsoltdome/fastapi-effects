from __future__ import annotations

import sys
from pathlib import Path

import pytest
from scripts import check
from scripts.check import built_distributions

ROOT = Path(__file__).resolve().parents[2]


def test_built_distributions_excludes_dist_metadata(tmp_path) -> None:
    wheel = tmp_path / "package-1.0-py3-none-any.whl"
    sdist = tmp_path / "package-1.0.tar.gz"
    for path in (wheel, sdist, tmp_path / ".gitignore", tmp_path / "notes.txt"):
        path.touch()

    assert built_distributions(tmp_path) == (wheel, sdist)


def test_check_runs_phase_aware_release_and_documentation_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    wheel = ROOT / "dist" / "package-1.0-py3-none-any.whl"
    sdist = ROOT / "dist" / "package-1.0.tar.gz"
    monkeypatch.setattr(check, "require", lambda command: None)
    monkeypatch.setattr(check, "run", lambda *command: commands.append(command))
    monkeypatch.setattr(check, "built_distributions", lambda directory: (wheel, sdist))

    assert check.main() == 0
    assert (
        sys.executable,
        "scripts/audit_release_candidate.py",
        "--phase",
        "auto",
    ) in commands
    assert (sys.executable, "scripts/check_documentation.py") in commands
    assert commands[-1] == ("twine", "check", str(wheel), str(sdist))


def test_release_workflow_uses_automatic_candidate_phase() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "scripts/check.py" in workflow
    assert "audit_release_candidate.py --phase auto" in workflow

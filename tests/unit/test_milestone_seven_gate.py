from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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

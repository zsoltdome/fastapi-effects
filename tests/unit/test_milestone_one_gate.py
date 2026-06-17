from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_milestone_one_structural_gate() -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/verify_milestone_one.py",
            "--skip-git-governance",
        ],
        cwd=ROOT,
        check=True,
    )

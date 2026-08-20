from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_milestone_eight_static_audit() -> None:
    subprocess.run(
        [sys.executable, "scripts/audit_milestone_eight.py"],
        cwd=ROOT,
        check=True,
    )

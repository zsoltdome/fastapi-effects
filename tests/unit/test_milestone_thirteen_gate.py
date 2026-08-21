from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_milestone_thirteen_local_gate() -> None:
    subprocess.run(
        [sys.executable, "scripts/audit_milestone_thirteen.py"],
        cwd=ROOT,
        check=True,
    )

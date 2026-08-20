#!/usr/bin/env python3
"""Execute dependency-free documented CLI and Python sample contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    for path in sorted((ROOT / "examples").rglob("*.py")):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    commands = (
        (sys.executable, "-m", "fastapi_mergen", "--version"),
        (sys.executable, "-m", "fastapi_mergen", "conformance", "spec"),
        (
            sys.executable,
            "-m",
            "fastapi_mergen",
            "webhooks",
            "validate-endpoint",
            "https://example.com/hooks",
        ),
    )
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    print("Documented dependency-free samples passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Execute the reviewed injected-failure matrix and emit machine-readable evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "chaos" / "scenarios.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("injected", "postgres", "all"), default="injected")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    modes = {"injected"} if args.profile == "injected" else {"injected", "postgres"}
    if "postgres" in modes and not os.getenv("FASTAPI_EFFECTS_TEST_ADMIN_DSN"):
        parser.error("postgres chaos requires FASTAPI_EFFECTS_TEST_ADMIN_DSN")
    selected = [scenario for scenario in manifest["scenarios"] if scenario["mode"] in modes]
    nodes = [str(scenario["node"]) for scenario in selected if scenario["node"]]
    started = datetime.now(UTC)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *nodes],
        cwd=ROOT,
        check=False,
    )
    report = {
        "schema_version": 1,
        "profile": args.profile,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "result": "pass" if completed.returncode == 0 else "fail",
        "scenario_ids": [scenario["id"] for scenario in selected],
        "environment_required": [
            scenario["id"] for scenario in manifest["scenarios"] if scenario["mode"] == "external"
        ],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

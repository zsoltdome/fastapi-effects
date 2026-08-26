#!/usr/bin/env python3
"""Fail closed until local, independent, partner, and observation RC gates exist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fastapi_mergen import __version__

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "planning" / "production-readiness-record.json"


def audit(phase: str = "final") -> dict[str, Any]:
    readiness = json.loads(RECORD.read_text(encoding="utf-8"))
    partners = readiness.get("partners", [])
    completed_partners = [
        partner
        for partner in partners
        if partner.get("status") == "complete"
        and partner.get("approved_by_partner") is True
        and partner.get("approved_by_maintainer") is True
        and partner.get("evidence_digest")
    ]
    security = readiness.get("independent_security_review", {})
    observation = readiness.get("rc_observation", {})
    approval = readiness.get("approval", {})
    selected_phase = _release_phase(phase)
    checks = {
        "release_version_matches_phase": (
            __version__ == "1.0.0rc1" if selected_phase == "rc" else __version__ == "1.0.0"
        ),
        "candidate_record_matches": readiness.get("candidate_version") == "1.0.0rc1",
        "two_completed_external_partners": len(completed_partners) >= 2,
        "independent_security_review_complete": security.get("status") == "complete",
        "no_unresolved_critical_or_high": security.get("unresolved_critical_or_high") is False,
    }
    if selected_phase == "final":
        checks.update(
            rc_observation_complete=observation.get("status") == "complete",
            observation_not_reset=observation.get("reset_by_contract_change") is False,
            no_observation_blockers=observation.get("release_blockers") == [],
            explicit_go_decision=approval.get("decision") == "go",
            two_approvers=len(approval.get("approvers", [])) >= 2,
        )
    if selected_phase == "pre-v1":
        checks = {"v1_readiness_gate_not_yet_applicable": True}
    return {
        "schema_version": 1,
        "version": __version__,
        "phase": selected_phase,
        "result": "pass" if all(checks.values()) else "blocked",
        "checks": checks,
        "blocking_checks": [name for name, passed in checks.items() if not passed],
    }


def _release_phase(requested: str) -> str:
    if requested != "auto":
        return requested
    if __version__ == "1.0.0rc1":
        return "rc"
    if __version__ == "1.0.0":
        return "final"
    return "pre-v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--phase", choices=("auto", "pre-v1", "rc", "final"), default="final")
    args = parser.parse_args()
    report = audit(args.phase)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_output is None:
        print(rendered, end="")
    else:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered, encoding="utf-8")
    if report["result"] == "pass" or args.allow_incomplete:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

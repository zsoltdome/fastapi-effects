#!/usr/bin/env python3
"""Fail closed until local, independent, partner, and observation RC gates exist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fastapi_mergen import __version__
from fastapi_mergen.readiness import (
    candidate_matches_release,
    classify_release_version,
    partner_is_complete,
    valid_digest,
    valid_observation_interval,
    validate_readiness_record,
)

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "planning" / "production-readiness-record.json"


def audit(
    phase: str = "final",
    *,
    readiness: dict[str, Any] | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    if readiness is None:
        readiness = json.loads(RECORD.read_text(encoding="utf-8"))
    current_version = __version__ if version is None else version
    selected_phase, phase_consistent = _release_phase(phase, version=current_version)
    selected_capabilities = readiness.get("selected_capabilities")
    if not isinstance(selected_capabilities, list) or any(
        not isinstance(item, str) for item in selected_capabilities
    ):
        selected_capabilities = []
    partners = readiness.get("partners", [])
    completed_partners = (
        [
            partner
            for partner in partners
            if partner_is_complete(
                partner,
                selected_capabilities=selected_capabilities,
            )
        ]
        if isinstance(partners, list)
        else []
    )
    security = readiness.get("independent_security_review", {})
    observation = readiness.get("rc_observation", {})
    approval = readiness.get("approval", {})
    record_errors = validate_readiness_record(
        readiness,
        require_candidate=selected_phase != "pre-v1",
    )
    if selected_phase == "pre-v1":
        checks = {
            "release_phase_supported_and_consistent": phase_consistent,
            "readiness_record_valid": not record_errors,
            "v1_readiness_gate_not_yet_applicable": True,
        }
        return _report(
            checks=checks,
            record_errors=record_errors,
            phase=selected_phase,
            version=current_version,
        )
    checks = {
        "release_phase_supported_and_consistent": phase_consistent,
        "readiness_record_valid": not record_errors,
        "release_version_matches_phase": classify_release_version(current_version)
        == selected_phase,
        "candidate_record_matches": candidate_matches_release(
            readiness.get("candidate_version"),
            current_version,
            phase=selected_phase,
        ),
        "candidate_source_and_artifacts_bound": (
            isinstance(readiness.get("candidate_source_commit"), str)
            and len(readiness["candidate_source_commit"]) == 40
            and isinstance(readiness.get("candidate_artifact_digests"), list)
            and bool(readiness["candidate_artifact_digests"])
            and all(valid_digest(value) for value in readiness["candidate_artifact_digests"])
        ),
        "two_completed_external_partners": len(completed_partners) >= 2,
        "independent_security_review_complete": (
            isinstance(security, dict)
            and security.get("status") == "complete"
            and valid_digest(security.get("evidence_digest"))
        ),
        "no_unresolved_critical_or_high": (
            isinstance(security, dict) and security.get("unresolved_critical_or_high") is False
        ),
    }
    if selected_phase == "final":
        checks.update(
            rc_observation_complete=(
                isinstance(observation, dict)
                and observation.get("status") == "complete"
                and valid_observation_interval(observation)
            ),
            observation_not_reset=(
                isinstance(observation, dict)
                and observation.get("reset_by_contract_change") is False
            ),
            no_observation_blockers=(
                isinstance(observation, dict) and observation.get("release_blockers") == []
            ),
            explicit_go_decision=(isinstance(approval, dict) and approval.get("decision") == "go"),
            two_approvers=_has_two_distinct_approvers(approval),
        )
    return _report(
        checks=checks,
        record_errors=record_errors,
        phase=selected_phase,
        version=current_version,
    )


def _report(
    *,
    checks: dict[str, bool],
    record_errors: tuple[str, ...],
    phase: str,
    version: str,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "version": version,
        "phase": phase,
        "result": "pass" if all(checks.values()) else "blocked",
        "checks": checks,
        "blocking_checks": [name for name, passed in checks.items() if not passed],
        "record_errors": list(record_errors),
    }


def _release_phase(requested: str, *, version: str) -> tuple[str, bool]:
    inferred = classify_release_version(version)
    if requested == "auto":
        return inferred, inferred != "unsupported"
    return requested, inferred == requested


def _has_two_distinct_approvers(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    approvers = value.get("approvers")
    return (
        isinstance(approvers, list)
        and len(approvers) >= 2
        and all(isinstance(item, str) and item for item in approvers)
        and len(approvers) == len(set(approvers))
    )


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

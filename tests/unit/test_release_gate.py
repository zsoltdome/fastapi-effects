from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from scripts.audit_release_candidate import audit

from fastapi_mergen.readiness import MANDATORY_PARTNER_EXERCISES


def test_release_gate_fails_closed_without_external_evidence() -> None:
    report = audit()
    assert report["result"] == "blocked"
    assert "two_completed_external_partners" in report["blocking_checks"]
    assert "rc_observation_complete" in report["blocking_checks"]
    assert "explicit_go_decision" in report["blocking_checks"]


def _ready_record() -> dict[str, Any]:
    digest_a = "a" * 64
    digest_b = "b" * 64
    artifact = "c" * 64
    exercises = sorted(MANDATORY_PARTNER_EXERCISES)
    return {
        "schema_version": 2,
        "candidate_version": "1.0.0rc1",
        "candidate_source_commit": "d" * 40,
        "candidate_artifact_digests": [artifact],
        "selected_capabilities": ["core", "webhook"],
        "partners": [
            {
                "id": "partner-a",
                "environment_owner": "owner-a",
                "status": "complete",
                "deployment_class": "production_like",
                "capabilities": ["core", "webhook"],
                "exercises": exercises,
                "evidence_ids": ["evidence-a"],
                "evidence_digest": digest_a,
                "issues": [],
                "approved_by_partner": True,
                "approved_by_maintainer": True,
            },
            {
                "id": "partner-b",
                "environment_owner": "owner-b",
                "status": "complete",
                "deployment_class": "production",
                "capabilities": ["core", "webhook"],
                "exercises": exercises,
                "evidence_ids": ["evidence-b"],
                "evidence_digest": digest_b,
                "issues": [],
                "approved_by_partner": True,
                "approved_by_maintainer": True,
            },
        ],
        "independent_security_review": {
            "status": "complete",
            "evidence_digest": "e" * 64,
            "unresolved_critical_or_high": False,
            "issues": [],
        },
        "rc_observation": {
            "status": "complete",
            "candidate_version": "1.0.0rc1",
            "candidate_source_commit": "d" * 40,
            "candidate_artifact_digests": [artifact],
            "started_at": "2026-10-01T00:00:00+00:00",
            "completed_at": "2026-10-08T00:00:00+00:00",
            "reset_by_contract_change": False,
            "release_blockers": [],
        },
        "approval": {
            "decision": "go",
            "decided_at": "2026-10-08T01:00:00+00:00",
            "approvers": ["approver-a", "approver-b"],
        },
    }


def test_release_gate_is_phase_aware() -> None:
    ready = _ready_record()
    pre_v1 = {
        "schema_version": 2,
        "candidate_version": None,
        "candidate_source_commit": None,
        "candidate_artifact_digests": [],
        "selected_capabilities": [],
        "partners": [],
        "independent_security_review": {
            "status": "pending",
            "evidence_digest": None,
            "unresolved_critical_or_high": None,
            "issues": [],
        },
        "rc_observation": {
            "status": "not_started",
            "candidate_version": None,
            "candidate_source_commit": None,
            "candidate_artifact_digests": [],
            "started_at": None,
            "completed_at": None,
            "reset_by_contract_change": False,
            "release_blockers": [],
        },
        "approval": {"decision": "no-go", "decided_at": None, "approvers": []},
    }
    assert audit("pre-v1", readiness=pre_v1, version="0.11.0a1")["result"] == "pass"
    assert audit("auto", readiness=pre_v1, version="0.11.0a1")["result"] == "pass"

    incomplete_rc = deepcopy(ready)
    incomplete_rc["partners"] = []
    incomplete_rc["independent_security_review"] = pre_v1["independent_security_review"]
    incomplete_rc["approval"] = pre_v1["approval"]
    assert audit("rc", readiness=incomplete_rc, version="1.0.0rc1")["result"] == "blocked"

    assert audit("rc", readiness=ready, version="1.0.0rc1")["result"] == "pass"
    assert audit("final", readiness=ready, version="1.0.0")["result"] == "pass"
    assert audit("auto", readiness=ready, version="1.0.0rc1")["phase"] == "rc"
    assert audit("auto", readiness=ready, version="1.0.0")["phase"] == "final"

    unobserved = deepcopy(ready)
    unobserved["rc_observation"] = {
        "status": "not_started",
        "candidate_version": None,
        "candidate_source_commit": None,
        "candidate_artifact_digests": [],
        "started_at": None,
        "completed_at": None,
        "reset_by_contract_change": False,
        "release_blockers": [],
    }
    assert audit("rc", readiness=unobserved, version="1.0.0rc1")["result"] == "pass"
    assert audit("final", readiness=unobserved, version="1.0.0")["result"] == "blocked"


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda value: value["partners"][0].update(evidence_digest="x"),
            "partners.0.evidence_digest",
        ),
        (
            lambda value: value["partners"][1].update(environment_owner="owner-a"),
            "partners.duplicate_environment_owner",
        ),
        (
            lambda value: value["partners"][0].update(deployment_class="demo"),
            "partners.0.deployment_class",
        ),
        (
            lambda value: value["approval"].update(approvers=["same", "same"]),
            "approval.approvers",
        ),
        (
            lambda value: value["rc_observation"].update(candidate_artifact_digests=["f" * 64]),
            "rc_observation.candidate_artifact_digests",
        ),
        (
            lambda value: value["partners"][0].update(exercises=[]),
            "partners.0.exercises",
        ),
        (
            lambda value: value["partners"][1].update(evidence_digest="a" * 64),
            "partners.duplicate_evidence_digest",
        ),
        (
            lambda value: value["partners"][0].update(
                issues=[
                    {
                        "severity": "high",
                        "status": "open",
                        "contract_breaking": False,
                    }
                ]
            ),
            "partners.0.issues",
        ),
        (
            lambda value: value["independent_security_review"].update(evidence_digest="x"),
            "independent_security_review.evidence_digest",
        ),
        (
            lambda value: value["independent_security_review"].update(
                issues=[
                    {
                        "severity": "critical",
                        "status": "open",
                        "contract_breaking": True,
                    }
                ]
            ),
            "independent_security_review.issues",
        ),
        (
            lambda value: value["rc_observation"].update(started_at="2026-10-09T00:00:00+00:00"),
            "rc_observation.interval",
        ),
        (
            lambda value: value["rc_observation"].update(candidate_source_commit="f" * 40),
            "rc_observation.candidate_source_commit",
        ),
        (
            lambda value: value["approval"].update(decided_at="2026-10-01T01:00:00+00:00"),
            "approval.before_observation",
        ),
    ],
)
def test_release_gate_rejects_placeholder_or_mismatched_evidence(
    mutation: Callable[[dict[str, Any]], None],
    expected_error: str,
) -> None:
    readiness = _ready_record()
    mutation(readiness)
    report = audit("final", readiness=readiness, version="1.0.0")
    assert report["result"] == "blocked"
    assert expected_error in report["record_errors"]

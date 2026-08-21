from __future__ import annotations

from scripts.audit_release_candidate import audit


def test_release_gate_fails_closed_without_external_evidence() -> None:
    report = audit()
    assert report["result"] == "blocked"
    assert "two_completed_external_partners" in report["blocking_checks"]
    assert "rc_observation_complete" in report["blocking_checks"]
    assert "explicit_go_decision" in report["blocking_checks"]

"""Small assertion helpers for adapter and deployment test suites."""

from __future__ import annotations

from fastapi_mergen.conformance.certification import CertificationDecision, decide
from fastapi_mergen.conformance.models import ConformanceReport


def assert_certified(report: ConformanceReport) -> CertificationDecision:
    """Raise a bounded assertion when a conformance report is not certified."""

    decision = decide(report)
    if decision.certified:
        return decision
    details = [
        *(f"missing:{item}" for item in decision.missing_invariants),
        *(f"failed:{item}" for item in decision.failed_checks),
        *(f"error:{item}" for item in decision.errored_checks),
        *(f"skipped:{item}" for item in decision.skipped_checks),
    ]
    raise AssertionError("Mergen conformance failed: " + ", ".join(details))

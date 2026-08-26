from __future__ import annotations

from scripts.verify_hosted_release_checks import missing_successful_checks


def test_hosted_release_checks_require_success_for_every_name() -> None:
    required = frozenset({"compat", "security", "conformance"})
    runs: list[dict[str, object]] = [
        {"name": "compat", "status": "completed", "conclusion": "success"},
        {"name": "security", "status": "completed", "conclusion": "failure"},
        {"name": "conformance", "status": "in_progress", "conclusion": None},
    ]

    assert missing_successful_checks(runs, required=required) == (
        "conformance",
        "security",
    )


def test_hosted_release_checks_accept_duplicate_successful_runs() -> None:
    required = frozenset({"compat"})
    runs: list[dict[str, object]] = [
        {"name": "compat", "status": "completed", "conclusion": "failure"},
        {"name": "compat", "status": "completed", "conclusion": "success"},
    ]

    assert missing_successful_checks(runs, required=required) == ()

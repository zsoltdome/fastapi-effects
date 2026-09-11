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


def test_hosted_checks_require_trusted_workflow_app_repository_and_head() -> None:
    required = frozenset({"compat"})
    workflow = {"compat": ".github/workflows/compatibility.yml"}
    base: dict[str, object] = {
        "name": "compat",
        "status": "completed",
        "conclusion": "success",
        "head_sha": "a" * 40,
        "app": {"slug": "github-actions"},
        "workflow_path": ".github/workflows/compatibility.yml",
        "workflow_head_sha": "a" * 40,
        "workflow_conclusion": "success",
        "workflow_repository": "owner/project",
        "completed_at": "2026-09-14T10:00:00Z",
        "id": 1,
    }
    for field, invalid in (
        ("head_sha", "b" * 40),
        ("app", {"slug": "untrusted-app"}),
        ("workflow_path", ".github/workflows/untrusted.yml"),
        ("workflow_repository", "attacker/project"),
    ):
        run = dict(base)
        run[field] = invalid
        assert missing_successful_checks(
            [run],
            required=required,
            expected_head_sha="a" * 40,
            expected_repository="owner/project",
            required_workflows=workflow,
        ) == ("compat",)


def test_latest_trusted_duplicate_must_be_successful() -> None:
    required = frozenset({"compat"})
    workflow = {"compat": ".github/workflows/compatibility.yml"}
    runs: list[dict[str, object]] = []
    for identifier, conclusion in ((1, "success"), (2, "failure")):
        runs.append(
            {
                "name": "compat",
                "status": "completed",
                "conclusion": conclusion,
                "head_sha": "a" * 40,
                "app": {"slug": "github-actions"},
                "workflow_path": ".github/workflows/compatibility.yml",
                "workflow_head_sha": "a" * 40,
                "workflow_conclusion": "success",
                "workflow_repository": "owner/project",
                "completed_at": f"2026-09-14T10:00:0{identifier}Z",
                "id": identifier,
            }
        )

    assert missing_successful_checks(
        runs,
        required=required,
        expected_head_sha="a" * 40,
        expected_repository="owner/project",
        required_workflows=workflow,
    ) == ("compat",)

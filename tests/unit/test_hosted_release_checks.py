from __future__ import annotations

import httpx
import pytest
from scripts.verify_hosted_release_checks import (
    _load_authoritative_jobs,
    _workflow_path_matches,
    missing_successful_checks,
)


def _trusted_job(
    *,
    job_id: int,
    run_id: int,
    run_number: int,
    run_attempt: int = 1,
    job_status: str = "completed",
    job_conclusion: str | None = "success",
    workflow_status: str = "completed",
    workflow_conclusion: str | None = "success",
) -> dict[str, object]:
    return {
        "name": "compat",
        "status": job_status,
        "conclusion": job_conclusion,
        "head_sha": "a" * 40,
        "app": {"slug": "github-actions"},
        "workflow_path": ".github/workflows/compatibility.yml",
        "workflow_head_sha": "a" * 40,
        "workflow_status": workflow_status,
        "workflow_conclusion": workflow_conclusion,
        "workflow_repository": "owner/project",
        "workflow_source_repository": "owner/project",
        "workflow_event": "push",
        "workflow_head_branch": "main",
        "workflow_run_id": run_id,
        "workflow_run_number": run_number,
        "workflow_run_attempt": run_attempt,
        "completed_at": "2026-09-14T10:00:00Z",
        "id": job_id,
    }


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
    base = _trusted_job(job_id=1, run_id=101, run_number=1)
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
    runs = [
        _trusted_job(job_id=1, run_id=101, run_number=1),
        _trusted_job(
            job_id=2,
            run_id=102,
            run_number=2,
            workflow_conclusion="failure",
        ),
    ]

    assert missing_successful_checks(
        runs,
        required=required,
        expected_head_sha="a" * 40,
        expected_repository="owner/project",
        required_workflows=workflow,
    ) == ("compat",)


@pytest.mark.parametrize(
    ("workflow_status", "workflow_conclusion"),
    [("queued", None), ("in_progress", None), ("completed", "cancelled")],
)
def test_newer_authoritative_pending_or_cancelled_workflow_blocks_old_green(
    workflow_status: str,
    workflow_conclusion: str | None,
) -> None:
    required = frozenset({"compat"})
    policy = {"compat": ".github/workflows/compatibility.yml"}
    runs = [
        _trusted_job(job_id=1, run_id=101, run_number=1),
        _trusted_job(
            job_id=2,
            run_id=102,
            run_number=2,
            job_status=workflow_status,
            job_conclusion=workflow_conclusion,
            workflow_status=workflow_status,
            workflow_conclusion=workflow_conclusion,
        ),
    ]

    assert missing_successful_checks(
        runs,
        required=required,
        expected_head_sha="a" * 40,
        expected_repository="owner/project",
        required_workflows=policy,
        expected_event="push",
        expected_head_branch="main",
    ) == ("compat",)


def test_later_successful_full_rerun_attempt_is_authoritative() -> None:
    required = frozenset({"compat"})
    policy = {"compat": ".github/workflows/compatibility.yml"}
    runs = [
        _trusted_job(
            job_id=1,
            run_id=101,
            run_number=1,
            workflow_conclusion="failure",
        ),
        _trusted_job(job_id=2, run_id=101, run_number=1, run_attempt=2),
    ]

    assert (
        missing_successful_checks(
            runs,
            required=required,
            expected_head_sha="a" * 40,
            expected_repository="owner/project",
            required_workflows=policy,
            expected_event="push",
            expected_head_branch="main",
        )
        == ()
    )


def test_duplicate_required_job_name_in_one_attempt_is_ambiguous() -> None:
    policy = {"compat": ".github/workflows/compatibility.yml"}
    runs = [
        _trusted_job(job_id=1, run_id=101, run_number=1),
        _trusted_job(job_id=2, run_id=101, run_number=1),
    ]

    assert missing_successful_checks(
        runs,
        required=frozenset({"compat"}),
        expected_head_sha="a" * 40,
        expected_repository="owner/project",
        required_workflows=policy,
        expected_event="push",
        expected_head_branch="main",
    ) == ("compat",)


def test_workflow_first_client_uses_attempt_jobs_and_documented_path_ref_form() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if "/actions/workflows/" in request.url.path:
            filename = request.url.path.split("/actions/workflows/", 1)[1].split("/", 1)[0]
            workflow_path = f".github/workflows/{filename}"
            run_id = {
                "compatibility.yml": 101,
                "conformance.yml": 102,
                "security.yml": 103,
            }[filename]
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": run_id,
                            "run_number": 7,
                            "run_attempt": 2,
                            "status": "completed",
                            "conclusion": "success",
                            "path": workflow_path + "@main",
                            "head_sha": "a" * 40,
                            "head_branch": "main",
                            "event": "push",
                            "repository": {"full_name": "owner/project"},
                            "head_repository": {"full_name": "owner/project"},
                        }
                    ]
                },
            )
        if request.url.path.endswith("/attempts/2/jobs"):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 1001,
                            "name": "compat",
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                },
            )
        raise AssertionError(request.url)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs = _load_authoritative_jobs(
            client,
            api_url="https://api.github.test",
            repository="owner/project",
            commit="a" * 40,
            expected_head_branch="main",
        )

    assert len(jobs) == 3
    assert {job["workflow_run_attempt"] for job in jobs} == {2}
    assert any(path.endswith("/actions/workflows/compatibility.yml/runs") for path in seen_paths)
    assert any(path.endswith("/actions/runs/101/attempts/2/jobs") for path in seen_paths)


def test_main_workflow_path_does_not_accept_same_named_tag() -> None:
    assert _workflow_path_matches(
        ".github/workflows/ci.yml@main", ".github/workflows/ci.yml", "main"
    )
    assert _workflow_path_matches(
        ".github/workflows/ci.yml@refs/heads/main", ".github/workflows/ci.yml", "main"
    )
    assert not _workflow_path_matches(
        ".github/workflows/ci.yml@refs/tags/main", ".github/workflows/ci.yml", "main"
    )

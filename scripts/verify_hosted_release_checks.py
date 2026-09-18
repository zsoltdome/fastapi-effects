#!/usr/bin/env python3
"""Require successful hosted compatibility, security, and conformance checks."""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

REQUIRED_CHECKS = frozenset(
    {
        "compat-python-3.11",
        "compat-python-3.12",
        "compat-python-3.13",
        "compat-python-3.14",
        "compat-pg16-py311",
        "compat-pg18-py314",
        "compat-min-base",
        "compat-min-webhooks",
        "compat-min-otel",
        "compat-min-taskiq",
        "compat-min-fastmcp",
        "compat-latest-all",
        "Reference assurance suite",
        "Real complete / PostgreSQL 16",
        "Real complete / PostgreSQL 18",
        "audit",
    }
)
REQUIRED_WORKFLOWS = {
    **{
        name: ".github/workflows/compatibility.yml"
        for name in REQUIRED_CHECKS
        if name.startswith("compat-")
    },
    "Reference assurance suite": ".github/workflows/conformance.yml",
    "Real complete / PostgreSQL 16": ".github/workflows/conformance.yml",
    "Real complete / PostgreSQL 18": ".github/workflows/conformance.yml",
    "audit": ".github/workflows/security.yml",
}


def missing_successful_checks(
    runs: Iterable[dict[str, object]],
    *,
    required: frozenset[str] = REQUIRED_CHECKS,
    expected_head_sha: str | None = None,
    expected_repository: str | None = None,
    required_workflows: dict[str, str] | None = None,
    expected_event: str | None = None,
    expected_head_branch: str | None = None,
) -> tuple[str, ...]:
    workflow_policy = required_workflows or {}
    candidates: list[dict[str, object]] = []
    for run in runs:
        name = str(run.get("name"))
        if name not in required:
            continue
        if expected_head_sha is not None and run.get("head_sha") != expected_head_sha:
            continue
        app = run.get("app")
        if expected_head_sha is not None and (
            not isinstance(app, dict) or app.get("slug") != "github-actions"
        ):
            continue
        if expected_head_sha is not None and run.get("workflow_head_sha") != expected_head_sha:
            continue
        expected_workflow = workflow_policy.get(name)
        if expected_workflow is not None and run.get("workflow_path") != expected_workflow:
            continue
        if (
            expected_repository is not None
            and run.get("workflow_repository") != expected_repository
        ):
            continue
        if (
            expected_repository is not None
            and run.get("workflow_source_repository") != expected_repository
        ):
            continue
        if expected_event is not None and run.get("workflow_event") != expected_event:
            continue
        if (
            expected_head_branch is not None
            and run.get("workflow_head_branch") != expected_head_branch
        ):
            continue
        candidates.append(run)

    if expected_head_sha is not None and workflow_policy:
        strict_successful: set[str] = set()
        by_workflow: dict[str, frozenset[str]] = {}
        for name in required:
            path = workflow_policy.get(name)
            if path is not None:
                by_workflow[path] = frozenset(
                    candidate for candidate in required if workflow_policy.get(candidate) == path
                )
        for path, names in by_workflow.items():
            matching = [run for run in candidates if run.get("workflow_path") == path]
            identities: set[tuple[int, int, int]] = set()
            for run in matching:
                identity = _workflow_identity(run)
                if identity is not None:
                    identities.add(identity)
            if not identities:
                continue
            selected_identity = max(identities)
            selected = [run for run in matching if _workflow_identity(run) == selected_identity]
            representative = selected[0]
            if (
                representative.get("workflow_status") != "completed"
                or representative.get("workflow_conclusion") != "success"
            ):
                continue
            for name in names:
                jobs = [run for run in selected if run.get("name") == name]
                if len(jobs) != 1:
                    continue
                job = jobs[0]
                if job.get("status") == "completed" and job.get("conclusion") == "success":
                    strict_successful.add(name)
        return tuple(sorted(required - strict_successful))

    candidates_by_name: dict[str, list[dict[str, object]]] = {name: [] for name in required}
    for run in candidates:
        candidates_by_name[str(run.get("name"))].append(run)
    successful: set[str] = set()
    for name, matching in candidates_by_name.items():
        if not matching:
            continue
        _index, latest = max(
            enumerate(matching),
            key=lambda item: (*_job_order(item[1]), item[0]),
        )
        if latest.get("status") == "completed" and latest.get("conclusion") == "success":
            successful.add(name)
    return tuple(sorted(required - successful))


def _job_order(run: dict[str, object]) -> tuple[str, int]:
    completed_at = run.get("completed_at")
    identifier = run.get("id")
    return (
        completed_at if isinstance(completed_at, str) else "",
        identifier if isinstance(identifier, int) else -1,
    )


def _workflow_identity(run: dict[str, object]) -> tuple[int, int, int] | None:
    run_number = run.get("workflow_run_number")
    run_attempt = run.get("workflow_run_attempt")
    run_id = run.get("workflow_run_id")
    if (
        not isinstance(run_number, int)
        or isinstance(run_number, bool)
        or run_number <= 0
        or not isinstance(run_attempt, int)
        or isinstance(run_attempt, bool)
        or run_attempt <= 0
        or not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or run_id <= 0
    ):
        return None
    return run_number, run_attempt, run_id


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Hosted release check verification requires {name}.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--commit", default=os.getenv("GITHUB_SHA"))
    args = parser.parse_args()
    if not args.repository or not args.commit:
        raise RuntimeError("Hosted release check verification requires repository and commit.")
    api_url = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {_required_environment('GITHUB_TOKEN')}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(headers=headers, timeout=20) as client:
        runs = _load_authoritative_jobs(
            client,
            api_url=api_url,
            repository=args.repository,
            commit=args.commit,
            expected_head_branch="main",
        )
    missing = missing_successful_checks(
        runs,
        expected_head_sha=args.commit,
        expected_repository=args.repository,
        required_workflows=REQUIRED_WORKFLOWS,
        expected_event="push",
        expected_head_branch="main",
    )
    if missing:
        print("Missing successful hosted release checks: " + ", ".join(missing))
        return 1
    print(f"Verified {len(REQUIRED_CHECKS)} hosted release checks for {args.commit}.")
    return 0


def _load_authoritative_jobs(
    client: httpx.Client,
    *,
    api_url: str,
    repository: str,
    commit: str,
    expected_head_branch: str,
) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    for path in sorted(set(REQUIRED_WORKFLOWS.values())):
        workflows = _paginated_workflow_runs(
            client,
            (
                f"{api_url}/repos/{repository}/actions/workflows/"
                f"{quote(PurePosixPath(path).name, safe='')}/runs"
            ),
            commit=commit,
        )
        trusted = [
            workflow
            for workflow in workflows
            if _trusted_workflow(
                workflow,
                path=path,
                repository=repository,
                commit=commit,
                expected_head_branch=expected_head_branch,
            )
        ]
        if not trusted:
            continue
        selected = max(trusted, key=_workflow_order)
        run_id = selected["id"]
        run_attempt = selected["run_attempt"]
        attempt_jobs = _paginated_jobs(
            client,
            (f"{api_url}/repos/{repository}/actions/runs/{run_id}/attempts/{run_attempt}/jobs"),
        )
        destination = selected["repository"]
        source = selected["head_repository"]
        assert isinstance(destination, dict)
        assert isinstance(source, dict)
        for job in attempt_jobs:
            job["head_sha"] = commit
            job["app"] = {"slug": "github-actions"}
            job["workflow_path"] = path
            job["workflow_head_sha"] = selected["head_sha"]
            job["workflow_status"] = selected["status"]
            job["workflow_conclusion"] = selected["conclusion"]
            job["workflow_repository"] = destination["full_name"]
            job["workflow_source_repository"] = source["full_name"]
            job["workflow_event"] = selected["event"]
            job["workflow_head_branch"] = selected["head_branch"]
            job["workflow_run_id"] = run_id
            job["workflow_run_number"] = selected["run_number"]
            job["workflow_run_attempt"] = run_attempt
        jobs.extend(attempt_jobs)
    return jobs


def _paginated_workflow_runs(
    client: httpx.Client,
    url: str,
    *,
    commit: str,
) -> list[dict[str, object]]:
    runs: list[dict[str, object]] = []
    page = 1
    while True:
        response = client.get(
            url,
            params={
                "head_sha": commit,
                "event": "push",
                "exclude_pull_requests": "true",
                "per_page": 100,
                "page": page,
            },
        )
        response.raise_for_status()
        payload = response.json()
        values = payload.get("workflow_runs") if isinstance(payload, dict) else None
        if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
            raise RuntimeError("GitHub workflow-runs response is malformed.")
        runs.extend(values)
        if len(values) < 100:
            return runs
        page += 1


def _paginated_jobs(client: httpx.Client, url: str) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    page = 1
    while True:
        response = client.get(
            url,
            params={"filter": "all", "per_page": 100, "page": page},
        )
        response.raise_for_status()
        payload = response.json()
        values = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
            raise RuntimeError("GitHub jobs response is malformed.")
        jobs.extend(values)
        if len(values) < 100:
            return jobs
        page += 1


def _trusted_workflow(
    workflow: dict[str, object],
    *,
    path: str,
    repository: str,
    commit: str,
    expected_head_branch: str,
) -> bool:
    destination = workflow.get("repository")
    source = workflow.get("head_repository")
    return (
        _workflow_path_matches(workflow.get("path"), path, expected_head_branch)
        and workflow.get("head_sha") == commit
        and workflow.get("event") == "push"
        and workflow.get("head_branch") == expected_head_branch
        and isinstance(destination, dict)
        and destination.get("full_name") == repository
        and isinstance(source, dict)
        and source.get("full_name") == repository
        and _workflow_order(workflow) != (-1, -1, -1)
    )


def _workflow_path_matches(value: object, expected_path: str, expected_ref: str) -> bool:
    if value == expected_path:
        return True
    if not isinstance(value, str) or not value.startswith(expected_path + "@"):
        return False
    reference = value.removeprefix(expected_path + "@")
    return reference in {expected_ref, f"refs/heads/{expected_ref}"}


def _workflow_order(workflow: dict[str, object]) -> tuple[int, int, int]:
    values = (workflow.get("run_number"), workflow.get("run_attempt"), workflow.get("id"))
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in values
    ):
        return (-1, -1, -1)
    run_number, run_attempt, run_id = values
    assert isinstance(run_number, int)
    assert isinstance(run_attempt, int)
    assert isinstance(run_id, int)
    return run_number, run_attempt, run_id


if __name__ == "__main__":
    raise SystemExit(main())

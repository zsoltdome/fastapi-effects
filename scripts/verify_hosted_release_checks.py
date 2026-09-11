#!/usr/bin/env python3
"""Require successful hosted compatibility, security, and conformance checks."""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Iterable
from typing import Any

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
_RUN_ID = re.compile(r"/actions/runs/(?P<run_id>[0-9]+)(?:/|$)")


def missing_successful_checks(
    runs: Iterable[dict[str, object]],
    *,
    required: frozenset[str] = REQUIRED_CHECKS,
    expected_head_sha: str | None = None,
    expected_repository: str | None = None,
    required_workflows: dict[str, str] | None = None,
) -> tuple[str, ...]:
    workflow_policy = required_workflows or {}
    candidates: dict[str, list[dict[str, object]]] = {name: [] for name in required}
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
        if expected_head_sha is not None and (
            run.get("workflow_head_sha") != expected_head_sha
            or run.get("workflow_conclusion") != "success"
        ):
            continue
        expected_workflow = workflow_policy.get(name)
        if expected_workflow is not None and run.get("workflow_path") != expected_workflow:
            continue
        if (
            expected_repository is not None
            and run.get("workflow_repository") != expected_repository
        ):
            continue
        candidates[name].append(run)
    successful: set[str] = set()
    for name, matching in candidates.items():
        if not matching:
            continue
        _index, latest = max(
            enumerate(matching),
            key=lambda item: (*_run_order(item[1]), item[0]),
        )
        if latest.get("status") == "completed" and latest.get("conclusion") == "success":
            successful.add(name)
    return tuple(sorted(required - successful))


def _run_order(run: dict[str, object]) -> tuple[str, int]:
    completed_at = run.get("completed_at")
    identifier = run.get("id")
    return (
        completed_at if isinstance(completed_at, str) else "",
        identifier if isinstance(identifier, int) else -1,
    )


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
        runs = _paginated_check_runs(
            client,
            f"{api_url}/repos/{args.repository}/commits/{args.commit}/check-runs",
        )
        workflow_runs = _load_workflow_runs(
            client,
            api_url=api_url,
            repository=args.repository,
            check_runs=runs,
        )
    for run in runs:
        details_url = run.get("details_url")
        match = _RUN_ID.search(details_url) if isinstance(details_url, str) else None
        if match is None:
            continue
        workflow = workflow_runs.get(int(match.group("run_id")))
        if workflow is None:
            continue
        run["workflow_path"] = workflow.get("path")
        run["workflow_head_sha"] = workflow.get("head_sha")
        run["workflow_conclusion"] = workflow.get("conclusion")
        repository = workflow.get("repository")
        if isinstance(repository, dict):
            run["workflow_repository"] = repository.get("full_name")
    missing = missing_successful_checks(
        runs,
        expected_head_sha=args.commit,
        expected_repository=args.repository,
        required_workflows=REQUIRED_WORKFLOWS,
    )
    if missing:
        print("Missing successful hosted release checks: " + ", ".join(missing))
        return 1
    print(f"Verified {len(REQUIRED_CHECKS)} hosted release checks for {args.commit}.")
    return 0


def _paginated_check_runs(client: httpx.Client, url: str) -> list[dict[str, object]]:
    runs: list[dict[str, object]] = []
    page = 1
    while True:
        response = client.get(url, params={"per_page": 100, "page": page})
        response.raise_for_status()
        payload = response.json()
        values = payload.get("check_runs") if isinstance(payload, dict) else None
        if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
            raise RuntimeError("GitHub check-runs response is malformed.")
        runs.extend(values)
        if len(values) < 100:
            return runs
        page += 1


def _load_workflow_runs(
    client: httpx.Client,
    *,
    api_url: str,
    repository: str,
    check_runs: Iterable[dict[str, object]],
) -> dict[int, dict[str, Any]]:
    identifiers: set[int] = set()
    for run in check_runs:
        details_url = run.get("details_url")
        match = _RUN_ID.search(details_url) if isinstance(details_url, str) else None
        if match is not None:
            identifiers.add(int(match.group("run_id")))
    result: dict[int, dict[str, Any]] = {}
    for identifier in identifiers:
        response = client.get(
            f"{api_url}/repos/{repository}/actions/runs/{identifier}",
        )
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise RuntimeError("GitHub workflow-run response is malformed.")
        result[identifier] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())

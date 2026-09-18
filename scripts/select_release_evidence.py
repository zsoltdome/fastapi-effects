#!/usr/bin/env python3
"""Select one authoritative release-evidence workflow before checking success."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def select_release_run(
    runs: list[dict[str, object]],
    *,
    repository: str,
    source_commit: str,
    tag: str,
    workflow_path: str = ".github/workflows/release.yml",
    expected_run_id: int | None = None,
    expected_run_attempt: int | None = None,
) -> dict[str, object]:
    trusted = [
        run
        for run in runs
        if _trusted_run(
            run,
            repository=repository,
            source_commit=source_commit,
            tag=tag,
            workflow_path=workflow_path,
        )
    ]
    if not trusted:
        raise ValueError("No trusted release-evidence workflow exists for this tag and commit.")
    selected = max(trusted, key=_run_order)
    if selected.get("status") != "completed" or selected.get("conclusion") != "success":
        raise ValueError("The authoritative release-evidence workflow is not successful.")
    if expected_run_id is not None and selected.get("id") != expected_run_id:
        raise ValueError("The authoritative release-evidence workflow run changed.")
    if expected_run_attempt is not None and selected.get("run_attempt") != expected_run_attempt:
        raise ValueError("The authoritative release-evidence workflow attempt changed.")
    return selected


def load_runs(value: object) -> list[dict[str, object]]:
    pages = value if isinstance(value, list) else [value]
    result: list[dict[str, object]] = []
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("Workflow-runs response is malformed.")
        values = page.get("workflow_runs")
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            raise ValueError("Workflow-runs response is malformed.")
        result.extend(values)
    return result


def _trusted_run(
    run: dict[str, object],
    *,
    repository: str,
    source_commit: str,
    tag: str,
    workflow_path: str,
) -> bool:
    destination = run.get("repository")
    source = run.get("head_repository")
    return (
        run.get("head_sha") == source_commit
        and run.get("head_branch") == tag
        and run.get("event") == "push"
        and _workflow_path_matches(run.get("path"), workflow_path, tag)
        and isinstance(destination, dict)
        and destination.get("full_name") == repository
        and isinstance(source, dict)
        and source.get("full_name") == repository
        and _run_order(run) != (-1, -1, -1)
    )


def _workflow_path_matches(value: object, expected_path: str, expected_ref: str) -> bool:
    if value == expected_path:
        return True
    if not isinstance(value, str) or not value.startswith(expected_path + "@"):
        return False
    reference = value.removeprefix(expected_path + "@")
    return reference in {expected_ref, f"refs/tags/{expected_ref}"}


def _run_order(run: dict[str, object]) -> tuple[int, int, int]:
    values = (run.get("run_number"), run.get("run_attempt"), run.get("id"))
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in values
    ):
        return (-1, -1, -1)
    run_number, run_attempt, run_id = values
    assert isinstance(run_number, int)
    assert isinstance(run_attempt, int)
    assert isinstance(run_id, int)
    return run_number, run_attempt, run_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--expected-run-id", type=int)
    parser.add_argument("--expected-run-attempt", type=int)
    args = parser.parse_args()
    if (args.expected_run_id is None) != (args.expected_run_attempt is None):
        parser.error("expected run ID and attempt must be supplied together")
    value: Any = json.loads(args.input.read_text(encoding="utf-8"))
    selected = select_release_run(
        load_runs(value),
        repository=args.repository,
        source_commit=args.source_commit,
        tag=args.tag,
        expected_run_id=args.expected_run_id,
        expected_run_attempt=args.expected_run_attempt,
    )
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"run_id={selected['id']}\n")
        output.write(f"run_attempt={selected['run_attempt']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

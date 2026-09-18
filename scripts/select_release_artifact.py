#!/usr/bin/env python3
"""Select one immutable Actions artifact for an authoritative release attempt."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_DIGEST = re.compile(r"^sha256:(?P<value>[0-9a-f]{64})$")


def select_release_artifact(
    artifacts: list[dict[str, object]],
    *,
    name: str,
    run_id: int,
    source_commit: str,
    expected_artifact_id: int | None = None,
    expected_digest: str | None = None,
) -> dict[str, object]:
    candidates = [
        artifact
        for artifact in artifacts
        if _trusted_artifact(
            artifact,
            name=name,
            run_id=run_id,
            source_commit=source_commit,
        )
    ]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one trusted release-evidence artifact.")
    selected = candidates[0]
    digest = selected["digest"]
    assert isinstance(digest, str)
    match = _DIGEST.fullmatch(digest)
    assert match is not None
    digest_value = match.group("value")
    if expected_artifact_id is not None and selected.get("id") != expected_artifact_id:
        raise ValueError("The authoritative release-evidence artifact ID changed.")
    if expected_digest is not None and digest_value != expected_digest:
        raise ValueError("The authoritative release-evidence artifact digest changed.")
    return selected


def load_artifacts(value: object) -> list[dict[str, object]]:
    pages = value if isinstance(value, list) else [value]
    result: list[dict[str, object]] = []
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("Actions-artifacts response is malformed.")
        values = page.get("artifacts")
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            raise ValueError("Actions-artifacts response is malformed.")
        result.extend(values)
    return result


def _trusted_artifact(
    artifact: dict[str, object],
    *,
    name: str,
    run_id: int,
    source_commit: str,
) -> bool:
    artifact_id = artifact.get("id")
    size = artifact.get("size_in_bytes")
    workflow_run = artifact.get("workflow_run")
    digest = artifact.get("digest")
    return (
        isinstance(artifact_id, int)
        and not isinstance(artifact_id, bool)
        and artifact_id > 0
        and artifact.get("name") == name
        and artifact.get("expired") is False
        and isinstance(size, int)
        and not isinstance(size, bool)
        and size > 0
        and isinstance(digest, str)
        and _DIGEST.fullmatch(digest) is not None
        and isinstance(workflow_run, dict)
        and workflow_run.get("id") == run_id
        and workflow_run.get("head_sha") == source_commit
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--expected-artifact-id", type=int)
    parser.add_argument("--expected-digest")
    args = parser.parse_args()
    if (args.expected_artifact_id is None) != (args.expected_digest is None):
        parser.error("expected artifact ID and digest must be supplied together")
    value: Any = json.loads(args.input.read_text(encoding="utf-8"))
    selected = select_release_artifact(
        load_artifacts(value),
        name=args.name,
        run_id=args.run_id,
        source_commit=args.source_commit,
        expected_artifact_id=args.expected_artifact_id,
        expected_digest=args.expected_digest,
    )
    digest = selected["digest"]
    assert isinstance(digest, str)
    match = _DIGEST.fullmatch(digest)
    assert match is not None
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"artifact_id={selected['id']}\n")
        output.write(f"artifact_digest={match.group('value')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

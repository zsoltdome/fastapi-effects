from __future__ import annotations

import pytest
from scripts.select_release_evidence import load_runs, select_release_run


def _run(
    *,
    run_id: int,
    run_number: int,
    run_attempt: int = 1,
    status: str = "completed",
    conclusion: str | None = "success",
) -> dict[str, object]:
    return {
        "id": run_id,
        "run_number": run_number,
        "run_attempt": run_attempt,
        "status": status,
        "conclusion": conclusion,
        "head_sha": "a" * 40,
        "head_branch": "v0.12.0a1",
        "event": "push",
        "path": ".github/workflows/release.yml@refs/tags/v0.12.0a1",
        "repository": {"full_name": "owner/project"},
        "head_repository": {"full_name": "owner/project"},
    }


@pytest.mark.parametrize(
    ("status", "conclusion"),
    [("completed", "failure"), ("in_progress", None), ("queued", None)],
)
def test_newer_bad_authoritative_run_blocks_older_success(
    status: str,
    conclusion: str | None,
) -> None:
    runs = [
        _run(run_id=101, run_number=1),
        _run(
            run_id=102,
            run_number=2,
            status=status,
            conclusion=conclusion,
        ),
    ]

    with pytest.raises(ValueError, match="authoritative"):
        select_release_run(
            runs,
            repository="owner/project",
            source_commit="a" * 40,
            tag="v0.12.0a1",
        )


def test_latest_successful_rerun_attempt_is_selected() -> None:
    runs = [
        _run(run_id=101, run_number=1, conclusion="failure"),
        _run(run_id=101, run_number=1, run_attempt=2),
    ]

    selected = select_release_run(
        runs,
        repository="owner/project",
        source_commit="a" * 40,
        tag="v0.12.0a1",
    )

    assert selected["id"] == 101
    assert selected["run_attempt"] == 2


@pytest.mark.parametrize(
    ("expected_run_id", "expected_run_attempt"),
    [(102, 1), (101, 2)],
)
def test_authority_recheck_rejects_a_changed_run_or_attempt(
    expected_run_id: int,
    expected_run_attempt: int,
) -> None:
    with pytest.raises(ValueError, match="changed"):
        select_release_run(
            [_run(run_id=101, run_number=1)],
            repository="owner/project",
            source_commit="a" * 40,
            tag="v0.12.0a1",
            expected_run_id=expected_run_id,
            expected_run_attempt=expected_run_attempt,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("head_sha", "b" * 40),
        ("head_branch", "v0.11.0a1"),
        ("event", "workflow_dispatch"),
        ("path", ".github/workflows/untrusted.yml"),
        ("repository", {"full_name": "attacker/project"}),
        ("head_repository", {"full_name": "attacker/project"}),
    ],
)
def test_untrusted_release_run_identity_is_rejected(field: str, value: object) -> None:
    run = _run(run_id=101, run_number=1)
    run[field] = value

    with pytest.raises(ValueError, match="No trusted"):
        select_release_run(
            [run],
            repository="owner/project",
            source_commit="a" * 40,
            tag="v0.12.0a1",
        )


def test_paginated_gh_api_shape_is_flattened() -> None:
    first = _run(run_id=101, run_number=1)
    second = _run(run_id=102, run_number=2)

    assert load_runs([{"workflow_runs": [first]}, {"workflow_runs": [second]}]) == [
        first,
        second,
    ]


def test_release_selector_does_not_accept_same_named_branch() -> None:
    run = _run(run_id=101, run_number=1)
    run["path"] = ".github/workflows/release.yml@refs/heads/v0.12.0a1"

    with pytest.raises(ValueError, match="No trusted"):
        select_release_run(
            [run],
            repository="owner/project",
            source_commit="a" * 40,
            tag="v0.12.0a1",
        )

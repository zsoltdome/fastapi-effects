from __future__ import annotations

import pytest
from scripts.select_release_artifact import load_artifacts, select_release_artifact


def _artifact(
    *,
    artifact_id: int = 501,
    digest: str = "b" * 64,
    name: str = "release-evidence-v0.12.0a1-attempt-2",
    expired: bool = False,
) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": name,
        "size_in_bytes": 4096,
        "expired": expired,
        "digest": "sha256:" + digest,
        "workflow_run": {"id": 101, "head_sha": "a" * 40},
    }


def test_selects_one_attempt_specific_artifact_and_binds_identity() -> None:
    selected = select_release_artifact(
        [_artifact()],
        name="release-evidence-v0.12.0a1-attempt-2",
        run_id=101,
        source_commit="a" * 40,
        expected_artifact_id=501,
        expected_digest="b" * 64,
    )

    assert selected["id"] == 501


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("expired", "exactly one"),
        ("wrong_run", "exactly one"),
        ("wrong_sha", "exactly one"),
        ("bad_digest", "exactly one"),
        ("changed_id", "ID changed"),
        ("changed_digest", "digest changed"),
    ],
)
def test_rejects_untrusted_or_changed_artifact(mutation: str, message: str) -> None:
    artifact = _artifact()
    expected_id = 501
    expected_digest = "b" * 64
    if mutation == "expired":
        artifact["expired"] = True
    elif mutation == "wrong_run":
        artifact["workflow_run"] = {"id": 999, "head_sha": "a" * 40}
    elif mutation == "wrong_sha":
        artifact["workflow_run"] = {"id": 101, "head_sha": "c" * 40}
    elif mutation == "bad_digest":
        artifact["digest"] = "sha256:not-a-digest"
    elif mutation == "changed_id":
        expected_id = 999
    else:
        expected_digest = "c" * 64

    with pytest.raises(ValueError, match=message):
        select_release_artifact(
            [artifact],
            name="release-evidence-v0.12.0a1-attempt-2",
            run_id=101,
            source_commit="a" * 40,
            expected_artifact_id=expected_id,
            expected_digest=expected_digest,
        )


def test_duplicate_artifact_name_is_ambiguous() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        select_release_artifact(
            [_artifact(), _artifact(artifact_id=502)],
            name="release-evidence-v0.12.0a1-attempt-2",
            run_id=101,
            source_commit="a" * 40,
        )


def test_paginated_artifact_shape_is_flattened() -> None:
    first = _artifact()
    second = _artifact(artifact_id=502, name="unrelated")

    assert load_artifacts([{"artifacts": [first]}, {"artifacts": [second]}]) == [first, second]

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.release_artifacts import create_manifest, verify_manifest

COMMIT = "a" * 40
WORKFLOW = "mergen-institute/fastapi-mergen/.github/workflows/release.yml@refs/tags/v1.0.0#123"


def _candidate(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "candidate"
    (root / "dist").mkdir(parents=True)
    (root / "dist" / "fastapi_mergen-1.0.0-py3-none-any.whl").write_bytes(b"wheel")
    (root / "dist" / "fastapi_mergen-1.0.0.tar.gz").write_bytes(b"sdist")
    lock = tmp_path / "uv.lock"
    lock.write_bytes(b"locked")
    return root, lock


def test_release_manifest_binds_and_verifies_exact_distribution_bytes(tmp_path: Path) -> None:
    root, lock = _candidate(tmp_path)
    manifest = root / "build" / "release" / "artifact-manifest.json"
    create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
    )

    verified = verify_manifest(
        root=root,
        manifest_path=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
    )

    assert verified["source_commit"] == COMMIT
    assert len(verified["artifacts"]) == 2


@pytest.mark.parametrize("mutation", ["artifact", "lock", "extra"])
def test_release_manifest_rejects_changed_promotion_input(
    tmp_path: Path,
    mutation: str,
) -> None:
    root, lock = _candidate(tmp_path)
    manifest = root / "build" / "release" / "artifact-manifest.json"
    create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
    )
    if mutation == "artifact":
        (root / "dist" / "fastapi_mergen-1.0.0.tar.gz").write_bytes(b"changed")
    elif mutation == "lock":
        lock.write_bytes(b"changed")
    else:
        (root / "dist" / "unexpected.whl").write_bytes(b"unexpected")

    with pytest.raises(ValueError, match=r"Release artifact|Promoted|Canonical release"):
        verify_manifest(
            root=root,
            manifest_path=manifest,
            source_commit=COMMIT,
            package_version="1.0.0",
            workflow_identity=WORKFLOW,
            lock_file=lock,
        )


@pytest.mark.parametrize(
    ("source_commit", "package_version", "workflow_identity"),
    [
        ("b" * 40, "1.0.0", WORKFLOW),
        (COMMIT, "1.0.1", WORKFLOW),
        (
            COMMIT,
            "1.0.0",
            "mergen-institute/fastapi-mergen/.github/workflows/release.yml@refs/tags/v1.0.0#124",
        ),
    ],
)
def test_release_manifest_rejects_mismatched_source_version_or_workflow(
    tmp_path: Path,
    source_commit: str,
    package_version: str,
    workflow_identity: str,
) -> None:
    root, lock = _candidate(tmp_path)
    manifest = root / "build" / "release" / "artifact-manifest.json"
    create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
    )

    with pytest.raises(ValueError, match=r"source commit|version|workflow identity"):
        verify_manifest(
            root=root,
            manifest_path=manifest,
            source_commit=source_commit,
            package_version=package_version,
            workflow_identity=workflow_identity,
            lock_file=lock,
        )

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts.release_artifacts import create_manifest, verify_manifest

COMMIT = "a" * 40
WORKFLOW = "zsoltdome/fastapi-effects/.github/workflows/release.yml@refs/tags/v1.0.0#123.2"


def _candidate(tmp_path: Path, *, distribution_version: str = "1.0.0") -> tuple[Path, Path]:
    root = tmp_path / "candidate"
    (root / "dist").mkdir(parents=True)
    metadata = (
        f"Metadata-Version: 2.4\nName: fastapi-effects\nVersion: {distribution_version}\n\n"
    ).encode()
    wheel = root / "dist" / f"fastapi_effects-{distribution_version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"fastapi_effects-{distribution_version}.dist-info/METADATA",
            metadata,
        )
    sdist = root / "dist" / f"fastapi_effects-{distribution_version}.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        info = tarfile.TarInfo(f"fastapi_effects-{distribution_version}/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))
    lock = tmp_path / "uv.lock"
    lock.write_bytes(b"locked")
    return root, lock


def _canonical_digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _runtime_evidence(root: Path, lock: Path) -> tuple[Path, ...]:
    entries: list[dict[str, object]] = []
    evidence: list[Path] = []
    constraints_path = root / "build" / "release" / "artifact-lock-constraints.txt"
    constraints_path.parent.mkdir(parents=True, exist_ok=True)
    constraints_path.write_text("fastapi==0.141.1\n", encoding="utf-8")
    lock_digest = hashlib.sha256(lock.read_bytes()).hexdigest()
    constraints_digest = hashlib.sha256(constraints_path.read_bytes()).hexdigest()
    for kind, artifact in (
        ("wheel", next((root / "dist").glob("*.whl"))),
        ("sdist", next((root / "dist").glob("*.tar.gz"))),
    ):
        input_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        installed_digest = input_digest if kind == "wheel" else "d" * 64
        manifest = {
            "metadata": {
                "package.version": "1.0.0",
                "artifact.kind": kind,
                "artifact.input_sha256": input_digest,
                "artifact.installed_sha256": installed_digest,
                "artifact.package_origin_verified": True,
                "artifact.lock_sha256": lock_digest,
                "artifact.constraints_sha256": constraints_digest,
            }
        }
        manifest_path = root / "build" / "release" / f"{kind}-certification-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        report: dict[str, object] = {
            "profile": "complete",
            "status": "pass",
            "certified": True,
            "counts": {"pass": 1, "fail": 0, "skip": 0, "error": 0},
            "manifest_digest": _canonical_digest(manifest),
        }
        report["report_digest"] = _canonical_digest(report)
        report_path = root / "build" / "release" / f"{kind}-certification.json"
        report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        entry: dict[str, object] = {
            "artifact_kind": kind,
            "input_path": artifact.relative_to(root).as_posix(),
            "input_sha256": input_digest,
            "tests": ["tests/integration/test_example.py"],
            "installed_candidate_sha256": installed_digest,
            "installed_from": "wheel" if kind == "wheel" else "sdist-derived-wheel",
            "package_origin_verified": True,
            "lock_sha256": lock_digest,
            "constraints_path": "build/release/artifact-lock-constraints.txt",
            "constraints_sha256": constraints_digest,
            "certification": {
                "manifest_path": manifest_path.relative_to(root).as_posix(),
                "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "report_path": report_path.relative_to(root).as_posix(),
                "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            },
            "status": "passed",
        }
        if kind == "sdist":
            entry["derived_wheel_sha256"] = installed_digest
        entries.append(entry)
        evidence.extend((manifest_path, report_path))
    runtime_path = root / "build" / "release" / "artifact-runtime-results.json"
    runtime_path.write_text(
        json.dumps({"schema_version": 1, "status": "passed", "artifacts": entries}) + "\n",
        encoding="utf-8",
    )
    checks = [
        "historical_artifact_digest",
        "historical_artifact_installed",
        "historical_schema_created",
        "historical_data_seeded",
        "candidate_artifact_installed",
        "candidate_schema_upgraded",
        "seeded_data_preserved",
        "ownership_preserved",
        "runtime_roles_preserved",
        "grants_preserved",
        "forced_rls_preserved",
        "constraints_preserved",
        "indexes_preserved",
        "revision_markers_current",
    ]
    wheel = next((root / "dist").glob("*.whl"))
    historical_upgrade = root / "build" / "release" / "historical-upgrade-results.json"
    historical_upgrade.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "passed",
                "historical": {
                    "version": "0.11.0a1",
                    "filename": "fastapi_effects-0.11.0a1-py3-none-any.whl",
                    "url": "https://files.pythonhosted.org/example.whl",
                    "sha256": "e" * 64,
                },
                "candidate": {
                    "filename": wheel.name,
                    "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                },
                "targets": [
                    {
                        "target": f"postgresql-{major}",
                        "postgresql_major": major,
                        "server_version": f"{major}.1",
                        "status": "passed",
                        "checks": checks,
                        "historical_contract_sha256": "a" * 64,
                        "candidate_contract_sha256": "b" * 64,
                        "seed_counts": {"events": 1},
                        "revision_markers": {"core": 1},
                        "alembic_versions": ["0005_webhook_retention"],
                    }
                    for major in (16, 18)
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return (runtime_path, constraints_path, historical_upgrade, *evidence)


def test_release_manifest_binds_and_verifies_exact_distribution_bytes(tmp_path: Path) -> None:
    root, lock = _candidate(tmp_path)
    runtime_evidence = _runtime_evidence(root, lock)
    extra_evidence = root / "build" / "artifact-runtime" / "results.json"
    extra_evidence.parent.mkdir(parents=True)
    extra_evidence.write_text('{"status":"passed"}\n', encoding="utf-8")
    evidence = (*runtime_evidence, extra_evidence)
    manifest = root / "build" / "release" / "artifact-manifest.json"
    create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=evidence,
    )

    verified = verify_manifest(
        root=root,
        manifest_path=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=evidence,
    )

    assert verified["source_commit"] == COMMIT
    assert verified["workflow_run_id"] == 123
    assert verified["workflow_run_attempt"] == 2
    assert len(verified["artifacts"]) == 2
    assert "build/artifact-runtime/results.json" in {
        entry["path"] for entry in verified["evidence"]
    }


def test_release_manifest_rejects_changed_runtime_evidence(tmp_path: Path) -> None:
    root, lock = _candidate(tmp_path)
    runtime_evidence = _runtime_evidence(root, lock)
    extra_evidence = root / "build" / "artifact-runtime" / "results.json"
    extra_evidence.parent.mkdir(parents=True)
    extra_evidence.write_text('{"status":"passed"}\n', encoding="utf-8")
    evidence = (*runtime_evidence, extra_evidence)
    manifest = root / "build" / "release" / "artifact-manifest.json"
    create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=evidence,
    )
    extra_evidence.write_text('{"status":"failed"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="evidence failed identity"):
        verify_manifest(
            root=root,
            manifest_path=manifest,
            source_commit=COMMIT,
            package_version="1.0.0",
            workflow_identity=WORKFLOW,
            lock_file=lock,
            evidence_files=evidence,
        )


def test_release_manifest_validates_per_artifact_certification(tmp_path: Path) -> None:
    root, lock = _candidate(tmp_path)
    evidence = _runtime_evidence(root, lock)
    manifest = root / "build" / "release" / "artifact-manifest.json"

    created = create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=evidence,
    )

    assert len(created["evidence"]) == 7
    verify_manifest(
        root=root,
        manifest_path=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=evidence,
    )


def test_release_manifest_verifies_with_cli_style_relative_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, lock = _candidate(tmp_path)
    evidence = _runtime_evidence(root, lock)
    manifest = root / "build" / "release" / "artifact-manifest.json"
    create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=evidence,
    )
    monkeypatch.chdir(tmp_path)

    verify_manifest(
        root=Path("candidate"),
        manifest_path=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=tuple(path.relative_to(root) for path in evidence),
    )


@pytest.mark.parametrize(
    "missing_name",
    [
        "artifact-lock-constraints.txt",
        "artifact-runtime-results.json",
        "historical-upgrade-results.json",
        "wheel-certification-manifest.json",
        "wheel-certification.json",
        "sdist-certification-manifest.json",
        "sdist-certification.json",
    ],
)
def test_release_manifest_requires_every_runtime_evidence_file(
    tmp_path: Path,
    missing_name: str,
) -> None:
    root, lock = _candidate(tmp_path)
    evidence = tuple(path for path in _runtime_evidence(root, lock) if path.name != missing_name)

    with pytest.raises(ValueError, match="runtime evidence is missing"):
        create_manifest(
            root=root,
            output=root / "build" / "release" / "artifact-manifest.json",
            source_commit=COMMIT,
            package_version="1.0.0",
            workflow_identity=WORKFLOW,
            lock_file=lock,
            evidence_files=evidence,
        )


def test_release_manifest_rejects_distribution_metadata_for_another_version(
    tmp_path: Path,
) -> None:
    root, lock = _candidate(tmp_path, distribution_version="9.9.9")
    evidence = _runtime_evidence(root, lock)

    with pytest.raises(ValueError, match="distribution version"):
        create_manifest(
            root=root,
            output=root / "build" / "release" / "artifact-manifest.json",
            source_commit=COMMIT,
            package_version="1.0.0",
            workflow_identity=WORKFLOW,
            lock_file=lock,
            evidence_files=evidence,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("origin", "passing candidate"),
        ("artifact_digest", "passing candidate"),
        ("failed_certification", "complete-profile pass"),
        ("stale_certification_digest", "digest binding"),
        ("lock_digest", "passing candidate"),
        ("constraints_drift", "passing candidate"),
        ("certification_version", "package provenance"),
    ],
)
def test_release_manifest_rejects_invalid_artifact_runtime_evidence(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    root, lock = _candidate(tmp_path)
    evidence = _runtime_evidence(root, lock)
    runtime_path = next(path for path in evidence if path.name == "artifact-runtime-results.json")
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    wheel = runtime["artifacts"][0]
    if mutation == "origin":
        wheel["package_origin_verified"] = False
    elif mutation == "artifact_digest":
        wheel["input_sha256"] = "0" * 64
    elif mutation == "lock_digest":
        wheel["lock_sha256"] = "0" * 64
    elif mutation == "constraints_drift":
        constraints_path = next(path for path in evidence if path.name.endswith("constraints.txt"))
        constraints_path.write_text("fastapi==0.141.0\n", encoding="utf-8")
    elif mutation == "stale_certification_digest":
        wheel["certification"]["report_sha256"] = "0" * 64
    elif mutation == "certification_version":
        manifest_path = root / wheel["certification"]["manifest_path"]
        certification_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        certification_manifest["metadata"]["package.version"] = "9.9.9"
        manifest_path.write_text(
            json.dumps(certification_manifest) + "\n",
            encoding="utf-8",
        )
        wheel["certification"]["manifest_sha256"] = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
        report_path = root / wheel["certification"]["report_path"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["manifest_digest"] = _canonical_digest(certification_manifest)
        report.pop("report_digest")
        report["report_digest"] = _canonical_digest(report)
        report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        wheel["certification"]["report_sha256"] = hashlib.sha256(
            report_path.read_bytes()
        ).hexdigest()
    else:
        report_path = root / wheel["certification"]["report_path"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["certified"] = False
        report.pop("report_digest")
        report["report_digest"] = _canonical_digest(report)
        report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        wheel["certification"]["report_sha256"] = hashlib.sha256(
            report_path.read_bytes()
        ).hexdigest()
    runtime_path.write_text(json.dumps(runtime) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        create_manifest(
            root=root,
            output=root / "build" / "release" / "artifact-manifest.json",
            source_commit=COMMIT,
            package_version="1.0.0",
            workflow_identity=WORKFLOW,
            lock_file=lock,
            evidence_files=evidence,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("candidate_digest", "candidate wheel"),
        ("failed_target", "required checks"),
        ("missing_pg16", "PostgreSQL 16 and 18"),
    ],
)
def test_release_manifest_rejects_invalid_historical_upgrade_evidence(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    root, lock = _candidate(tmp_path)
    evidence = _runtime_evidence(root, lock)
    path = next(path for path in evidence if path.name == "historical-upgrade-results.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "candidate_digest":
        value["candidate"]["sha256"] = "0" * 64
    elif mutation == "failed_target":
        value["targets"][0]["status"] = "failed"
    else:
        value["targets"] = value["targets"][1:]
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        create_manifest(
            root=root,
            output=root / "build" / "release" / "artifact-manifest.json",
            source_commit=COMMIT,
            package_version="1.0.0",
            workflow_identity=WORKFLOW,
            lock_file=lock,
            evidence_files=evidence,
        )


@pytest.mark.parametrize("mutation", ["artifact", "lock", "extra"])
def test_release_manifest_rejects_changed_promotion_input(
    tmp_path: Path,
    mutation: str,
) -> None:
    root, lock = _candidate(tmp_path)
    evidence = _runtime_evidence(root, lock)
    manifest = root / "build" / "release" / "artifact-manifest.json"
    create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=evidence,
    )
    if mutation == "artifact":
        (root / "dist" / "fastapi_effects-1.0.0.tar.gz").write_bytes(b"changed")
    elif mutation == "lock":
        lock.write_bytes(b"changed")
    else:
        (root / "dist" / "unexpected.whl").write_bytes(b"unexpected")

    with pytest.raises(
        ValueError,
        match=r"Release artifact|Release distribution|Promoted|Canonical release",
    ):
        verify_manifest(
            root=root,
            manifest_path=manifest,
            source_commit=COMMIT,
            package_version="1.0.0",
            workflow_identity=WORKFLOW,
            lock_file=lock,
            evidence_files=evidence,
        )


@pytest.mark.parametrize(
    ("source_commit", "package_version", "workflow_identity"),
    [
        ("b" * 40, "1.0.0", WORKFLOW),
        (COMMIT, "1.0.1", WORKFLOW),
        (
            COMMIT,
            "1.0.0",
            "zsoltdome/fastapi-effects/.github/workflows/release.yml@refs/tags/v1.0.0#123.3",
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
    evidence = _runtime_evidence(root, lock)
    manifest = root / "build" / "release" / "artifact-manifest.json"
    create_manifest(
        root=root,
        output=manifest,
        source_commit=COMMIT,
        package_version="1.0.0",
        workflow_identity=WORKFLOW,
        lock_file=lock,
        evidence_files=evidence,
    )

    with pytest.raises(ValueError, match=r"source commit|version|workflow identity"):
        verify_manifest(
            root=root,
            manifest_path=manifest,
            source_commit=source_commit,
            package_version=package_version,
            workflow_identity=workflow_identity,
            lock_file=lock,
            evidence_files=evidence,
        )

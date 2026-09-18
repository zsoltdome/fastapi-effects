#!/usr/bin/env python3
"""Create and verify the canonical release-artifact identity manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Any

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.!+_-]{0,127}$")
_WORKFLOW = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@#+-]{0,511}$")
_WORKFLOW_RUN = re.compile(r"#(?P<run_id>[1-9][0-9]*)\.(?P<run_attempt>[1-9][0-9]*)$")
_REQUIRED_RUNTIME_EVIDENCE = frozenset(
    {
        "build/release/artifact-lock-constraints.txt",
        "build/release/artifact-runtime-results.json",
        "build/release/wheel-certification-manifest.json",
        "build/release/wheel-certification.json",
        "build/release/sdist-certification-manifest.json",
        "build/release/sdist-certification.json",
    }
)
_MAXIMUM_METADATA_BYTES = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_manifest(
    *,
    root: Path,
    output: Path,
    source_commit: str,
    package_version: str,
    workflow_identity: str,
    lock_file: Path,
    evidence_files: tuple[Path, ...] = (),
) -> dict[str, Any]:
    _validate_identity(source_commit, package_version, workflow_identity)
    workflow_run_id, workflow_run_attempt = _workflow_run_identity(workflow_identity)
    distributions = _distributions(root)
    _validate_distribution_metadata(distributions, package_version=package_version)
    evidence_paths = _evidence_paths(root, evidence_files)
    lock_digest = sha256_file(lock_file)
    _validate_artifact_runtime_evidence(
        root,
        distributions,
        evidence_paths,
        lock_digest=lock_digest,
        package_version=package_version,
    )
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "source_commit": source_commit,
        "package_version": package_version,
        "workflow_identity": workflow_identity,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "lock_sha256": lock_digest,
        "artifacts": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in distributions
        ],
        "evidence": [_file_entry(root, path) for path in evidence_paths],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(
    *,
    root: Path,
    manifest_path: Path,
    source_commit: str,
    package_version: str,
    workflow_identity: str,
    lock_file: Path,
    evidence_files: tuple[Path, ...] = (),
) -> dict[str, Any]:
    _validate_identity(source_commit, package_version, workflow_identity)
    workflow_run_id, workflow_run_attempt = _workflow_run_identity(workflow_identity)
    distributions = _distributions(root)
    _validate_distribution_metadata(distributions, package_version=package_version)
    lock_digest = sha256_file(lock_file)
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise ValueError("Release artifact manifest schema is invalid.")
    if value.get("source_commit") != source_commit:
        raise ValueError("Release artifact source commit does not match promotion target.")
    if value.get("package_version") != package_version:
        raise ValueError("Release artifact version does not match promotion target.")
    if value.get("workflow_identity") != workflow_identity:
        raise ValueError("Release artifact workflow identity does not match promotion target.")
    if (
        value.get("workflow_run_id") != workflow_run_id
        or value.get("workflow_run_attempt") != workflow_run_attempt
    ):
        raise ValueError("Release artifact workflow run attempt does not match promotion target.")
    if value.get("lock_sha256") != lock_digest:
        raise ValueError("Release artifact lock identity does not match promotion target.")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ValueError("Release artifact manifest must contain one wheel and one sdist.")
    expected_paths: set[str] = set()
    for entry in artifacts:
        if not isinstance(entry, dict):
            raise ValueError("Release artifact manifest entry is invalid.")
        relative = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("size")
        if (
            not isinstance(relative, str)
            or not relative.startswith("dist/")
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 1
        ):
            raise ValueError("Release artifact manifest entry is unsafe.")
        path = root / relative
        if (
            not path.resolve().is_relative_to(root.resolve())
            or not path.is_file()
            or path.stat().st_size != size
            or sha256_file(path) != digest
        ):
            raise ValueError(f"Release artifact failed identity verification: {relative}")
        expected_paths.add(relative)
    actual_paths = {path.relative_to(root).as_posix() for path in distributions}
    if actual_paths != expected_paths:
        raise ValueError("Promoted distribution set differs from the approved manifest.")
    evidence = value.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("Release artifact evidence manifest is invalid.")
    expected_evidence = {
        path.relative_to(root.resolve()).as_posix(): path
        for path in _evidence_paths(root, evidence_files)
    }
    if len(evidence) != len(expected_evidence):
        raise ValueError("Release artifact evidence set differs from the approved manifest.")
    for entry in evidence:
        if not isinstance(entry, dict):
            raise ValueError("Release artifact evidence entry is invalid.")
        relative = entry.get("path")
        if not isinstance(relative, str) or relative not in expected_evidence:
            raise ValueError("Release artifact evidence entry is unsafe.")
        path = expected_evidence[relative]
        if entry != _file_entry(root, path):
            raise ValueError(f"Release evidence failed identity verification: {relative}")
    _validate_artifact_runtime_evidence(
        root,
        distributions,
        tuple(expected_evidence.values()),
        lock_digest=lock_digest,
        package_version=package_version,
    )
    return value


def _distributions(root: Path) -> tuple[Path, Path]:
    wheels = tuple(root.glob("dist/*.whl"))
    sdists = tuple(root.glob("dist/*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Canonical release requires exactly one wheel and one sdist.")
    return wheels[0], sdists[0]


def _validate_distribution_metadata(
    distributions: tuple[Path, Path],
    *,
    package_version: str,
) -> None:
    for distribution in distributions:
        metadata = _distribution_metadata(distribution)
        name = metadata.get("Name")
        version = metadata.get("Version")
        if not isinstance(name, str) or _normalized_project_name(name) != "fastapi-mergen":
            raise ValueError("Release distribution project name is invalid.")
        if version != package_version:
            raise ValueError("Release distribution version does not match the promotion target.")


def _distribution_metadata(path: Path) -> Any:
    try:
        if path.name.endswith(".whl"):
            with zipfile.ZipFile(path) as archive:
                zip_candidates = [
                    info
                    for info in archive.infolist()
                    if info.filename.endswith(".dist-info/METADATA")
                    and not info.is_dir()
                    and info.file_size <= _MAXIMUM_METADATA_BYTES
                ]
                if len(zip_candidates) != 1:
                    raise ValueError("Wheel must contain exactly one bounded METADATA file.")
                payload = archive.read(zip_candidates[0])
        else:
            with tarfile.open(path, "r:gz") as archive:
                tar_candidates = [
                    member
                    for member in archive.getmembers()
                    if member.isfile()
                    and len(Path(member.name).parts) == 2
                    and Path(member.name).name == "PKG-INFO"
                    and member.size <= _MAXIMUM_METADATA_BYTES
                ]
                if len(tar_candidates) != 1:
                    raise ValueError("Sdist must contain exactly one bounded root PKG-INFO file.")
                stream = archive.extractfile(tar_candidates[0])
                if stream is None:
                    raise ValueError("Sdist PKG-INFO is unreadable.")
                payload = stream.read(_MAXIMUM_METADATA_BYTES + 1)
    except (tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
        raise ValueError("Release distribution metadata is unreadable.") from exc
    if len(payload) > _MAXIMUM_METADATA_BYTES:
        raise ValueError("Release distribution metadata is oversized.")
    return BytesParser(policy=default).parsebytes(payload)


def _normalized_project_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _evidence_paths(root: Path, values: tuple[Path, ...]) -> tuple[Path, ...]:
    result: list[Path] = []
    resolved_root = root.resolve()
    for value in values:
        path = value if value.is_absolute() else root / value
        resolved = path.resolve()
        if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
            raise ValueError("Release evidence path is unsafe or missing.")
        result.append(resolved)
    if len(result) != len(set(result)):
        raise ValueError("Release evidence paths must be unique.")
    return tuple(sorted(result))


def _file_entry(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root.resolve()).as_posix(),
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }


def _validate_artifact_runtime_evidence(
    root: Path,
    distributions: tuple[Path, Path],
    evidence_paths: tuple[Path, ...],
    *,
    lock_digest: str,
    package_version: str,
) -> None:
    evidence = {path.relative_to(root.resolve()).as_posix(): path for path in evidence_paths}
    missing = _REQUIRED_RUNTIME_EVIDENCE - evidence.keys()
    if missing:
        raise ValueError(f"Release artifact runtime evidence is missing: {sorted(missing)}")
    runtime_path = evidence.get("build/release/artifact-runtime-results.json")
    assert runtime_path is not None
    constraints_path = evidence["build/release/artifact-lock-constraints.txt"]
    constraints_digest = sha256_file(constraints_path)
    value = _json_object(runtime_path, "Artifact runtime evidence")
    if set(value) != {"schema_version", "status", "artifacts"} or (
        value.get("schema_version") != 1 or value.get("status") != "passed"
    ):
        raise ValueError("Artifact runtime evidence did not record a passing schema-v1 run.")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ValueError("Artifact runtime evidence must contain wheel and sdist results.")
    distributions_by_kind = {
        "wheel" if path.name.endswith(".whl") else "sdist": path for path in distributions
    }
    observed_kinds: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("Artifact runtime result is invalid.")
        kind = item.get("artifact_kind")
        if kind not in distributions_by_kind or kind in observed_kinds:
            raise ValueError("Artifact runtime evidence repeats or omits an artifact kind.")
        observed_kinds.add(kind)
        expected_keys = {
            "artifact_kind",
            "input_path",
            "input_sha256",
            "tests",
            "installed_candidate_sha256",
            "installed_from",
            "package_origin_verified",
            "lock_sha256",
            "constraints_path",
            "constraints_sha256",
            "certification",
            "status",
        }
        if kind == "sdist":
            expected_keys.add("derived_wheel_sha256")
        if set(item) != expected_keys:
            raise ValueError("Artifact runtime result fields are incomplete or unknown.")
        distribution = distributions_by_kind[kind]
        relative_distribution = distribution.relative_to(root).as_posix()
        input_digest = sha256_file(distribution)
        installed_digest = item.get("installed_candidate_sha256")
        tests = item.get("tests")
        if (
            item.get("status") != "passed"
            or item.get("package_origin_verified") is not True
            or item.get("input_path") != relative_distribution
            or item.get("input_sha256") != input_digest
            or item.get("lock_sha256") != lock_digest
            or item.get("constraints_path") != "build/release/artifact-lock-constraints.txt"
            or item.get("constraints_sha256") != constraints_digest
            or not isinstance(installed_digest, str)
            or _DIGEST.fullmatch(installed_digest) is None
            or not isinstance(tests, list)
            or not tests
            or any(not isinstance(test, str) or not test for test in tests)
        ):
            raise ValueError("Artifact runtime result is not bound to a passing candidate.")
        if kind == "wheel":
            if item.get("installed_from") != "wheel" or installed_digest != input_digest:
                raise ValueError("Wheel runtime result does not bind the input wheel.")
        elif (
            item.get("installed_from") != "sdist-derived-wheel"
            or item.get("derived_wheel_sha256") != installed_digest
        ):
            raise ValueError("Sdist runtime result does not bind its derived wheel.")
        _validate_certification_evidence(
            kind=kind,
            item=item,
            input_digest=input_digest,
            installed_digest=installed_digest,
            lock_digest=lock_digest,
            constraints_digest=constraints_digest,
            package_version=package_version,
            evidence=evidence,
        )
    if observed_kinds != {"wheel", "sdist"}:
        raise ValueError("Artifact runtime evidence must cover wheel and sdist.")


def _validate_certification_evidence(
    *,
    kind: str,
    item: dict[str, Any],
    input_digest: str,
    installed_digest: str,
    lock_digest: str,
    constraints_digest: str,
    package_version: str,
    evidence: dict[str, Path],
) -> None:
    certification = item.get("certification")
    expected_keys = {
        "manifest_path",
        "manifest_sha256",
        "report_path",
        "report_sha256",
    }
    if not isinstance(certification, dict) or set(certification) != expected_keys:
        raise ValueError("Artifact certification binding is incomplete.")
    manifest_relative = certification.get("manifest_path")
    report_relative = certification.get("report_path")
    expected_manifest = f"build/release/{kind}-certification-manifest.json"
    expected_report = f"build/release/{kind}-certification.json"
    if manifest_relative != expected_manifest or report_relative != expected_report:
        raise ValueError("Artifact certification paths do not match the artifact kind.")
    manifest_path = evidence.get(expected_manifest)
    report_path = evidence.get(expected_report)
    if manifest_path is None or report_path is None:
        raise ValueError("Artifact certification files are missing from release evidence.")
    if certification.get("manifest_sha256") != sha256_file(manifest_path) or (
        certification.get("report_sha256") != sha256_file(report_path)
    ):
        raise ValueError("Artifact certification digest binding is invalid.")
    manifest = _json_object(manifest_path, "Artifact certification manifest")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict) or (
        metadata.get("artifact.kind") != kind
        or metadata.get("package.version") != package_version
        or metadata.get("artifact.input_sha256") != input_digest
        or metadata.get("artifact.installed_sha256") != installed_digest
        or metadata.get("artifact.package_origin_verified") is not True
        or metadata.get("artifact.lock_sha256") != lock_digest
        or metadata.get("artifact.constraints_sha256") != constraints_digest
    ):
        raise ValueError("Artifact certification manifest has invalid package provenance.")
    report = _json_object(report_path, "Artifact certification report")
    report_digest = report.pop("report_digest", None)
    counts = report.get("counts")
    if (
        report.get("profile") != "complete"
        or report.get("status") != "pass"
        or report.get("certified") is not True
        or not isinstance(counts, dict)
        or any(counts.get(name) != 0 for name in ("fail", "skip", "error"))
        or report.get("manifest_digest") != _canonical_json_sha256(manifest)
        or report_digest != _canonical_json_sha256(report)
    ):
        raise ValueError("Artifact certification report is not a valid complete-profile pass.")


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _canonical_json_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_identity(
    source_commit: str,
    package_version: str,
    workflow_identity: str,
) -> None:
    if _COMMIT.fullmatch(source_commit) is None:
        raise ValueError("Release source commit must be a full lowercase Git SHA.")
    if _VERSION.fullmatch(package_version) is None:
        raise ValueError("Release package version is invalid.")
    if _WORKFLOW.fullmatch(workflow_identity) is None:
        raise ValueError("Release workflow identity is invalid.")
    _workflow_run_identity(workflow_identity)


def _workflow_run_identity(workflow_identity: str) -> tuple[int, int]:
    match = _WORKFLOW_RUN.search(workflow_identity)
    if match is None:
        raise ValueError("Release workflow identity must bind a run ID and attempt.")
    return int(match.group("run_id")), int(match.group("run_attempt"))


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--source-commit", required=True)
        command.add_argument("--package-version", required=True)
        command.add_argument("--workflow-identity", required=True)
        command.add_argument("--lock-file", type=Path, required=True)
        command.add_argument("--evidence-file", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.command == "create":
        create_manifest(
            root=args.root,
            output=args.manifest,
            source_commit=args.source_commit,
            package_version=args.package_version,
            workflow_identity=args.workflow_identity,
            lock_file=args.lock_file,
            evidence_files=tuple(args.evidence_file),
        )
    else:
        verify_manifest(
            root=args.root,
            manifest_path=args.manifest,
            source_commit=args.source_commit,
            package_version=args.package_version,
            workflow_identity=args.workflow_identity,
            lock_file=args.lock_file,
            evidence_files=tuple(args.evidence_file),
        )
    print(f"Release artifact manifest {args.command} passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

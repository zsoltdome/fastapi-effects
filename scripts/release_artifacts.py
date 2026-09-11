#!/usr/bin/env python3
"""Create and verify the canonical release-artifact identity manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.!+_-]{0,127}$")
_WORKFLOW = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@#+-]{0,511}$")


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
) -> dict[str, Any]:
    _validate_identity(source_commit, package_version, workflow_identity)
    distributions = _distributions(root)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "source_commit": source_commit,
        "package_version": package_version,
        "workflow_identity": workflow_identity,
        "lock_sha256": sha256_file(lock_file),
        "artifacts": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in distributions
        ],
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
) -> dict[str, Any]:
    _validate_identity(source_commit, package_version, workflow_identity)
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Release artifact manifest schema is invalid.")
    if value.get("source_commit") != source_commit:
        raise ValueError("Release artifact source commit does not match promotion target.")
    if value.get("package_version") != package_version:
        raise ValueError("Release artifact version does not match promotion target.")
    if value.get("workflow_identity") != workflow_identity:
        raise ValueError("Release artifact workflow identity does not match promotion target.")
    if value.get("lock_sha256") != sha256_file(lock_file):
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
    actual_paths = {path.relative_to(root).as_posix() for path in _distributions(root)}
    if actual_paths != expected_paths:
        raise ValueError("Promoted distribution set differs from the approved manifest.")
    return value


def _distributions(root: Path) -> tuple[Path, Path]:
    wheels = tuple(root.glob("dist/*.whl"))
    sdists = tuple(root.glob("dist/*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Canonical release requires exactly one wheel and one sdist.")
    return wheels[0], sdists[0]


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
    args = parser.parse_args()
    if args.command == "create":
        create_manifest(
            root=args.root,
            output=args.manifest,
            source_commit=args.source_commit,
            package_version=args.package_version,
            workflow_identity=args.workflow_identity,
            lock_file=args.lock_file,
        )
    else:
        verify_manifest(
            root=args.root,
            manifest_path=args.manifest,
            source_commit=args.source_commit,
            package_version=args.package_version,
            workflow_identity=args.workflow_identity,
            lock_file=args.lock_file,
        )
    print(f"Release artifact manifest {args.command} passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

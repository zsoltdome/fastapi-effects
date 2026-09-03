#!/usr/bin/env python3
"""Execute dependency-free documented CLI and Python sample contracts."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "planning" / "documentation-scenario-inventory.json"
CAPABILITY_LEDGER = ROOT / "docs" / "planning" / "capability-evidence-ledger.json"
EXECUTABLE_FENCE_LANGUAGES = frozenset({"bash", "console", "python", "sh", "shell"})
CLASSIFICATIONS = frozenset({"executed", "manual_operator", "syntax_checked", "historical"})
EVIDENCE_STAGES = frozenset(
    {
        "OPEN",
        "IMPLEMENTED",
        "LOCAL_VERIFIED",
        "HOSTED_VERIFIED",
        "EXTERNALLY_VALIDATED",
        "RELEASED",
    }
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _markdown_paths() -> tuple[Path, ...]:
    return (
        ROOT / "README.md",
        *sorted((ROOT / "docs").rglob("*.md")),
        *sorted((ROOT / "examples").rglob("README.md")),
    )


def _documented_blocks() -> dict[tuple[str, int], dict[str, Any]]:
    blocks: dict[tuple[str, int], dict[str, Any]] = {}
    opening = re.compile(r"```([^ ]*)$")
    for path in _markdown_paths():
        relative = path.relative_to(ROOT).as_posix()
        language: str | None = None
        content: list[str] = []
        ordinal = 0
        start_line = 0
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if language is None:
                match = opening.fullmatch(line.strip())
                if match is not None and match.group(1) in EXECUTABLE_FENCE_LANGUAGES:
                    language = match.group(1)
                    content = []
                    ordinal += 1
                    start_line = line_number
            elif line.strip() == "```":
                body = "\n".join(content) + "\n"
                blocks[(relative, ordinal)] = {
                    "language": language,
                    "line": start_line,
                    "sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "body": body,
                }
                language = None
            else:
                content.append(line)
        if language is not None:
            raise AssertionError(f"Unclosed executable fence in {relative}:{start_line}")
    return blocks


def _load_inventory() -> dict[str, Any]:
    value = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise AssertionError("Documentation scenario inventory must use schema version 1.")
    return value


def repository_reference(reference: str) -> Path:
    """Resolve one evidence reference without allowing paths outside the repository."""

    raw_path = reference.split("::", 1)[0]
    if not raw_path or Path(raw_path).is_absolute():
        raise AssertionError(f"Evidence reference must be repository-relative: {reference}.")
    candidate = (ROOT / raw_path).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise AssertionError(f"Evidence reference escapes the repository: {reference}.") from exc
    if not candidate.is_file():
        raise AssertionError(f"Evidence reference is not a repository file: {reference}.")
    return candidate


def _validate_inventory() -> None:
    inventory = _load_inventory()
    documented = _documented_blocks()
    declared: dict[tuple[str, int], dict[str, Any]] = {}
    identifiers: set[str] = set()
    for item in inventory.get("blocks", []):
        if not isinstance(item, dict):
            raise AssertionError("Documentation block inventory entries must be objects.")
        identifier = item.get("id")
        path = item.get("path")
        ordinal = item.get("ordinal")
        classification = item.get("classification")
        evidence = item.get("evidence")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise AssertionError("Documentation block IDs must be nonempty and unique.")
        identifiers.add(identifier)
        if not isinstance(path, str) or not isinstance(ordinal, int):
            raise AssertionError(f"Documentation block {identifier} has an invalid location.")
        if classification not in CLASSIFICATIONS:
            raise AssertionError(f"Documentation block {identifier} has no valid classification.")
        if not isinstance(evidence, list) or not all(isinstance(v, str) and v for v in evidence):
            raise AssertionError(f"Documentation block {identifier} has invalid evidence.")
        if classification == "executed" and not evidence:
            raise AssertionError(f"Executed documentation block {identifier} needs evidence.")
        for reference in evidence:
            try:
                repository_reference(reference)
            except AssertionError as exc:
                raise AssertionError(
                    f"Documentation block {identifier} references missing evidence {reference}."
                ) from exc
        key = (path, ordinal)
        if key in declared:
            raise AssertionError(f"Duplicate documentation block location: {key}.")
        declared[key] = item

    if set(declared) != set(documented):
        missing = sorted(set(documented) - set(declared))
        stale = sorted(set(declared) - set(documented))
        raise AssertionError(
            f"Documentation inventory mismatch; missing={missing!r}; stale={stale!r}."
        )
    for key, item in declared.items():
        observed = documented[key]
        if item.get("language") != observed["language"] or item.get("sha256") != observed["sha256"]:
            raise AssertionError(
                f"Documentation block changed without inventory review: {key} "
                f"(current line {observed['line']})."
            )
        if observed["language"] == "python" and item["classification"] != "manual_operator":
            compile(
                observed["body"],
                f"{key[0]}:{observed['line']}",
                "exec",
                flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
            )

    journeys = inventory.get("journeys")
    required_journeys = {
        "artifact_install",
        "fastmcp",
        "quickstart",
        "relay",
        "replay",
        "taskiq",
        "webhook_lifecycle",
    }
    if not isinstance(journeys, list):
        raise AssertionError("Documentation journey inventory is missing.")
    journey_ids: set[str] = set()
    for item in journeys:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise AssertionError("Documentation journeys must be named objects.")
        journey_ids.add(item["id"])
    if journey_ids != required_journeys:
        raise AssertionError(
            f"Documentation journeys must be exhaustive; observed {sorted(journey_ids)}."
        )
    for item in journeys:
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise AssertionError(f"Documentation journey {item.get('id')} needs evidence.")
        for reference in evidence:
            if not isinstance(reference, str):
                raise AssertionError(
                    f"Documentation journey {item.get('id')} has missing evidence {reference}."
                )
            try:
                repository_reference(reference)
            except AssertionError as exc:
                raise AssertionError(
                    f"Documentation journey {item.get('id')} has missing evidence {reference}."
                ) from exc


def _validate_capability_ledger() -> None:
    ledger = json.loads(CAPABILITY_LEDGER.read_text(encoding="utf-8"))
    if not isinstance(ledger, dict) or ledger.get("schema_version") != 1:
        raise AssertionError("Capability ledger must use schema version 1.")
    if not _aware_timestamp(ledger.get("recorded_at")):
        raise AssertionError("Capability ledger must have an aware timestamp.")
    if not isinstance(ledger.get("package_version"), str) or not ledger["package_version"]:
        raise AssertionError("Capability ledger must name its package version.")
    source = ledger.get("source")
    if (
        not isinstance(source, dict)
        or SOURCE_COMMIT.fullmatch(str(source.get("base_commit"))) is None
        or not isinstance(source.get("state"), str)
        or not isinstance(source.get("release_evidence_authority"), bool)
    ):
        raise AssertionError("Capability ledger has an invalid source binding.")
    if SHA256.fullmatch(str(ledger.get("lock_sha256"))) is None:
        raise AssertionError("Capability ledger has an invalid lock digest.")
    authoritative_digests = ledger.get("artifact_digests")
    if (
        not isinstance(authoritative_digests, list)
        or any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            for value in authoritative_digests
            if isinstance(value, str)
        )
        or any(not isinstance(value, str) for value in authoritative_digests)
    ):
        raise AssertionError("Capability ledger has invalid authoritative artifact digests.")
    local_digests = ledger.get("local_non_authoritative_artifact_digests")
    if not isinstance(local_digests, dict) or any(
        not isinstance(name, str)
        or Path(name).name != name
        or not name.endswith((".whl", ".tar.gz"))
        or not isinstance(digest, str)
        or SHA256.fullmatch(digest) is None
        for name, digest in local_digests.items()
    ):
        raise AssertionError("Capability ledger has invalid local artifact digests.")
    known_artifact_digests = set(authoritative_digests) | {
        f"sha256:{digest}" for digest in local_digests.values()
    }
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        raise AssertionError("Capability ledger must contain entries.")
    capabilities: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise AssertionError("Capability ledger entries must be objects.")
        capability = entry.get("capability")
        if not isinstance(capability, str) or not capability or capability in capabilities:
            raise AssertionError("Capability ledger IDs must be nonempty and unique.")
        capabilities.add(capability)
        status = entry.get("status")
        if status not in EVIDENCE_STAGES:
            raise AssertionError(f"Capability {capability} has an invalid evidence stage.")
        if not isinstance(entry.get("owner"), str) or not entry["owner"]:
            raise AssertionError(f"Capability {capability} has no owner.")
        source_commit = entry.get("source_commit")
        if not isinstance(source_commit, str) or SOURCE_COMMIT.fullmatch(source_commit) is None:
            raise AssertionError(f"Capability {capability} has no valid source commit.")
        if source_commit != source["base_commit"]:
            raise AssertionError(f"Capability {capability} has a mismatched source commit.")
        for field in (
            "applicable_stages",
            "artifact_digests",
            "infrastructure",
            "dependency_versions",
        ):
            value = entry.get(field)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise AssertionError(f"Capability {capability} has an invalid {field} field.")
        if any(stage not in EVIDENCE_STAGES - {"OPEN"} for stage in entry["applicable_stages"]):
            raise AssertionError(f"Capability {capability} has invalid applicable stages.")
        if any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            for digest in entry["artifact_digests"]
        ):
            raise AssertionError(f"Capability {capability} has a malformed artifact digest.")
        if not set(entry["artifact_digests"]).issubset(known_artifact_digests):
            raise AssertionError(f"Capability {capability} has an unbound artifact digest.")
        evidence_command = entry.get("evidence_command")
        if status != "OPEN" and (not isinstance(evidence_command, str) or not evidence_command):
            raise AssertionError(f"Capability {capability} has no evidence command.")
        if evidence_command is not None and not isinstance(evidence_command, str):
            raise AssertionError(f"Capability {capability} has an invalid evidence command.")
        if not isinstance(entry.get("result"), str) or not entry["result"]:
            raise AssertionError(f"Capability {capability} has no result.")
        if not _aware_timestamp(entry.get("recorded_at")):
            raise AssertionError(f"Capability {capability} has no timestamp.")
        evidence_location = entry.get("evidence_location")
        if evidence_location is not None:
            if not isinstance(evidence_location, str):
                raise AssertionError(f"Capability {capability} has invalid evidence location.")
            try:
                repository_reference(evidence_location)
            except AssertionError as exc:
                raise AssertionError(
                    f"Capability {capability} has invalid evidence location."
                ) from exc


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 64:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def main() -> int:
    _validate_inventory()
    _validate_capability_ledger()
    for path in sorted((ROOT / "examples").rglob("*.py")):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    commands = (
        (sys.executable, "-m", "fastapi_mergen", "--version"),
        (sys.executable, "-m", "fastapi_mergen", "conformance", "spec"),
        (
            sys.executable,
            "-m",
            "fastapi_mergen",
            "webhooks",
            "validate-endpoint",
            "https://example.com/hooks",
        ),
    )
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    print("Documented dependency-free samples passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

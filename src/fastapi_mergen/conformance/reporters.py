"""Credential-safe JSON, JUnit, SARIF, and Markdown reporters."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi_mergen.conformance.certification import decide
from fastapi_mergen.conformance.models import CheckStatus, ConformanceReport
from fastapi_mergen.conformance.safety import JsonValue, clean_text
from fastapi_mergen.errors import MergenConfigurationError


class ReportFormat(StrEnum):
    """Stable public report encodings."""

    JSON = "json"
    JUNIT = "junit"
    SARIF = "sarif"
    MARKDOWN = "markdown"


def canonical_report_bytes(report: ConformanceReport) -> bytes:
    """Return deterministic JSON bytes used for artifact identity."""

    return json.dumps(
        report.as_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def report_digest(report: ConformanceReport) -> str:
    """Return the report SHA-256 digest."""

    return hashlib.sha256(canonical_report_bytes(report)).hexdigest()


def render_report(report: ConformanceReport, format: ReportFormat | str) -> str:
    """Render a report without including exception messages or raw credentials."""

    selected = ReportFormat(format)
    if selected is ReportFormat.JSON:
        value = report.as_dict()
        value["report_digest"] = report_digest(report)
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "
"
    if selected is ReportFormat.JUNIT:
        return _junit(report)
    if selected is ReportFormat.SARIF:
        return _sarif(report)
    return _markdown(report)


def write_report(path: str | Path, content: str) -> Path:
    """Atomically write private-by-default evidence without following destination links."""

    target = Path(path)
    if not target.name or target.name in {".", ".."}:
        raise MergenConfigurationError("Conformance output path is invalid.")
    parent = target.parent.resolve(strict=True)
    if not parent.is_dir():
        raise MergenConfigurationError("Conformance output parent is not a directory.")
    destination = parent / target.name
    if destination.exists() and destination.is_dir():
        raise MergenConfigurationError("Conformance output path is a directory.")
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="
") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return destination


def _junit(report: ConformanceReport) -> str:
    counts = report.counts()
    suite = ET.Element(
        "testsuite",
        {
            "name": f"fastapi-mergen-{report.profile.value}",
            "tests": str(len(report.results)),
            "failures": str(counts[CheckStatus.FAIL.value]),
            "errors": str(counts[CheckStatus.ERROR.value]),
            "skipped": str(counts[CheckStatus.SKIP.value]),
            "timestamp": report.started_at.isoformat(),
            "time": f"{sum(item.duration_ms for item in report.results) / 1000:.3f}",
        },
    )
    properties = ET.SubElement(suite, "properties")
    for name, value in (
        ("contract_version", report.contract_version),
        ("manifest_digest", report.manifest_digest),
        ("report_digest", report_digest(report)),
        ("certified", str(report.certified).lower()),
    ):
        ET.SubElement(properties, "property", {"name": name, "value": value})
    for result in report.results:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": result.invariant.value,
                "name": result.check_id,
                "time": f"{result.duration_ms / 1000:.3f}",
            },
        )
        if result.status is CheckStatus.FAIL:
            ET.SubElement(case, "failure", {"message": result.summary, "type": "invariant"})
        elif result.status is CheckStatus.ERROR:
            ET.SubElement(
                case,
                "error",
                {"message": result.summary, "type": result.exception_type or "conformance"},
            )
        elif result.status is CheckStatus.SKIP:
            ET.SubElement(case, "skipped", {"message": result.summary})
        evidence = ET.SubElement(case, "system-out")
        evidence.text = json.dumps(result.evidence, sort_keys=True, separators=(",", ":"))
    tree = ET.ElementTree(suite)
    ET.indent(tree, space="  ")
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "
"


def _sarif(report: ConformanceReport) -> str:
    rules = []
    results = []
    seen: set[str] = set()
    for item in report.results:
        if item.check_id not in seen:
            seen.add(item.check_id)
            rules.append(
                {
                    "id": item.check_id,
                    "name": item.invariant.value,
                    "shortDescription": {"text": item.summary},
                    "properties": {
                        "invariant": item.invariant.value,
                        "severity": item.severity.value,
                    },
                }
            )
        if item.status is CheckStatus.PASS:
            continue
        level = {
            CheckStatus.FAIL: "error",
            CheckStatus.ERROR: "error",
            CheckStatus.SKIP: "warning",
        }[item.status]
        results.append(
            {
                "ruleId": item.check_id,
                "level": level,
                "message": {"text": item.summary},
                "properties": {
                    "status": item.status.value,
                    "invariant": item.invariant.value,
                    "remediation": item.remediation,
                    "evidence": item.evidence,
                },
            }
        )
    document: dict[str, JsonValue] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "FastAPI-Mergen Boundary Conformance",
                        "informationUri": "https://github.com/mergen-institute/fastapi-mergen",
                        "rules": rules,
                        "version": report.contract_version,
                    }
                },
                "automationDetails": {"id": str(report.run_id)},
                "properties": {
                    "profile": report.profile.value,
                    "manifest_digest": report.manifest_digest,
                    "report_digest": report_digest(report),
                    "certified": report.certified,
                },
                "results": results,
            }
        ],
    }
    return json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "
"


def _markdown(report: ConformanceReport) -> str:
    decision = decide(report)
    lines = [
        "# FastAPI-Mergen conformance report",
        "",
        f"- Profile: `{report.profile.value}`",
        f"- Contract: `{report.contract_version}`",
        f"- Manifest SHA-256: `{report.manifest_digest}`",
        f"- Report SHA-256: `{report_digest(report)}`",
        f"- Certified: **{'yes' if decision.certified else 'no'}**",
        "",
        "| Check | Invariant | Status | Severity | Summary |",
        "|---|---|---:|---:|---|",
    ]
    for result in report.results:
        summary = clean_text(result.summary).replace("|", "\|").replace("
", " ")
        lines.append(
            f"| `{result.check_id}` | `{result.invariant.value}` | "
            f"**{result.status.value}** | {result.severity.value} | {summary} |"
        )
    if decision.missing_invariants:
        lines.extend(
            [
                "",
                "## Missing invariant evidence",
                "",
                ", ".join(f"`{value}`" for value in decision.missing_invariants),
            ]
        )
    return "
".join(lines) + "
"

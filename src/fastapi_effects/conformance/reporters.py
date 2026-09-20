"""Credential-safe JSON, JUnit, SARIF, and Markdown reporters."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import xml.etree.ElementTree as ET
from enum import StrEnum
from pathlib import Path

from fastapi_effects.conformance.certification import decide
from fastapi_effects.conformance.models import CheckStatus, ConformanceReport
from fastapi_effects.conformance.safety import JsonValue, clean_text
from fastapi_effects.errors import FastAPIEffectsConfigurationError


class ReportFormat(StrEnum):
    """Stable public report encodings."""

    JSON = "json"
    JUNIT = "junit"
    SARIF = "sarif"
    MARKDOWN = "markdown"


def canonical_report_bytes(report: ConformanceReport) -> bytes:
    """Return deterministic JSON bytes used for artifact identity."""

    return report.canonical_bytes()


def report_digest(report: ConformanceReport) -> str:
    """Return the report SHA-256 digest."""

    return report.digest


def render_report(report: ConformanceReport, output_format: ReportFormat | str) -> str:
    """Render a report without including exception messages or raw credentials."""

    selected = ReportFormat(output_format)
    if selected is ReportFormat.JSON:
        value = report.as_dict()
        value["report_digest"] = report_digest(report)
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
    if selected is ReportFormat.JUNIT:
        return _junit(report)
    if selected is ReportFormat.SARIF:
        return _sarif(report)
    return _markdown(report)


def write_report(path: str | Path, content: str) -> Path:
    """Atomically write private-by-default evidence without following links."""

    target = Path(path)
    if not target.name or target.name in {".", ".."}:
        raise FastAPIEffectsConfigurationError("Conformance output path is invalid.")
    try:
        parent = target.parent.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FastAPIEffectsConfigurationError("Conformance output parent does not exist.") from exc
    if not parent.is_dir():
        raise FastAPIEffectsConfigurationError("Conformance output parent is not a directory.")

    destination = parent / target.name
    if destination.exists():
        mode = destination.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise FastAPIEffectsConfigurationError("Conformance output path must not be a symlink.")
        if not stat.S_ISREG(mode):
            raise FastAPIEffectsConfigurationError(
                "Conformance output path must be a regular file."
            )

    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        try:
            directory_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return destination


def _junit(report: ConformanceReport) -> str:
    counts = report.counts()
    suite = ET.Element(
        "testsuite",
        {
            "name": f"fastapi_effects_{report.profile.value}",
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
            ET.SubElement(
                case,
                "failure",
                {"message": result.summary, "type": "invariant"},
            )
        elif result.status is CheckStatus.ERROR:
            ET.SubElement(
                case,
                "error",
                {
                    "message": result.summary,
                    "type": result.exception_type or "conformance",
                },
            )
        elif result.status is CheckStatus.SKIP:
            ET.SubElement(case, "skipped", {"message": result.summary})
        evidence = ET.SubElement(case, "system-out")
        evidence.text = json.dumps(
            result.evidence,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    ET.indent(suite, space="  ")
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def _sarif(report: ConformanceReport) -> str:
    rules: list[dict[str, JsonValue]] = []
    results: list[dict[str, JsonValue]] = []
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
    json_rules: list[JsonValue] = list(rules)
    json_results: list[JsonValue] = list(results)
    document: dict[str, JsonValue] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "FastAPI Effects Boundary Conformance",
                        "informationUri": ("https://github.com/zsoltdome/fastapi-effects"),
                        "rules": json_rules,
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
                "results": json_results,
            }
        ],
    }
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def _markdown(report: ConformanceReport) -> str:
    decision = decide(report)
    lines = [
        "# FastAPI Effects conformance report",
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
        summary = clean_text(result.summary).replace("|", "\\|").replace("\n", " ")
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
    return "\n".join(lines) + "\n"

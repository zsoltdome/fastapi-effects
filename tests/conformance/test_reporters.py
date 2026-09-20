from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from fastapi_effects.conformance import (
    CertificationProfile,
    ConformanceRunner,
    RunnerConfiguration,
)
from fastapi_effects.conformance.models import ConformanceReport
from fastapi_effects.conformance.reporters import ReportFormat, render_report, write_report
from fastapi_effects.errors import FastAPIEffectsConfigurationError
from fastapi_effects.testing import ReferenceBoundaryDriver


async def make_report() -> ConformanceReport:
    return await ConformanceRunner(RunnerConfiguration(profile=CertificationProfile.COMPLETE)).run(
        ReferenceBoundaryDriver()
    )


async def test_all_report_formats_are_parseable_and_secret_safe() -> None:
    report = await make_report()
    rendered = {
        output_format: render_report(report, output_format) for output_format in ReportFormat
    }
    json_payload = json.loads(rendered[ReportFormat.JSON])
    assert json_payload["report_digest"] == report.digest
    assert ConformanceReport.from_json(rendered[ReportFormat.JSON]) == report
    junit = ET.fromstring(rendered[ReportFormat.JUNIT])
    assert junit.tag == "testsuite"
    sarif = json.loads(rendered[ReportFormat.SARIF])
    assert sarif["version"] == "2.1.0"
    assert "Certified: **yes**" in rendered[ReportFormat.MARKDOWN]
    for content in rendered.values():
        assert "conformance-secret-canary-reference-key" not in content


async def test_atomic_report_write_is_private(tmp_path: Path) -> None:
    report = await make_report()
    destination = write_report(tmp_path / "report.json", render_report(report, "json"))
    assert destination.read_text(encoding="utf-8").endswith("\n")
    assert os.stat(destination).st_mode & 0o777 == 0o600


async def test_report_write_rejects_symlink_destination(tmp_path: Path) -> None:
    report = await make_report()
    target = tmp_path / "target.json"
    target.write_text("original", encoding="utf-8")
    link = tmp_path / "report.json"
    link.symlink_to(target)
    with pytest.raises(FastAPIEffectsConfigurationError, match="symlink"):
        write_report(link, render_report(report, "json"))
    assert target.read_text(encoding="utf-8") == "original"

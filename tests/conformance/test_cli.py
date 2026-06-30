from __future__ import annotations

import json
from pathlib import Path

from fastapi_mergen.cli.main import main
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.models import ConformanceReport
from fastapi_mergen.testing import ReferenceBoundaryDriver


def test_reference_run_emits_verifiable_json(capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(
        [
            "conformance",
            "run",
            "--reference",
            "--profile",
            "complete",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    report = ConformanceReport.from_json(captured.out)
    assert report.certified
    assert not captured.err


def test_reference_fault_returns_nonzero(capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(
        [
            "conformance",
            "run",
            "--reference",
            "--profile",
            "complete",
            "--fault",
            "stale_lease_accepted",
        ]
    )
    report = ConformanceReport.from_json(capsys.readouterr().out)
    assert code == 1
    assert not report.certified


def test_manifest_input_requires_no_driver_source(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    manifest = ReferenceBoundaryDriver().manifest
    path = tmp_path / "manifest.json"
    path.write_text(manifest.to_json(), encoding="utf-8")
    code = main(["conformance", "manifest", "--input", str(path)])
    captured = capsys.readouterr()
    assert code == 0
    assert CapabilityManifest.from_json(captured.out) == manifest


def test_manifest_rejects_ambiguous_sources(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "manifest.json"
    path.write_text(ReferenceBoundaryDriver().manifest.to_json(), encoding="utf-8")
    code = main(
        [
            "conformance",
            "manifest",
            "--input",
            str(path),
            "--reference",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "exactly one" in captured.err


def test_adapter_factory_is_loaded_explicitly(capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(
        [
            "conformance",
            "run",
            "--adapter",
            "tests.conformance.fixtures:create_async_driver",
            "--profile",
            "core",
        ]
    )
    report = ConformanceReport.from_json(capsys.readouterr().out)
    assert code == 0
    assert report.certified


def test_verify_binds_report_to_manifest(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    report_path = tmp_path / "report.json"
    manifest_path = tmp_path / "manifest.json"
    assert (
        main(
            [
                "conformance",
                "run",
                "--reference",
                "--profile",
                "complete",
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    manifest_path.write_text(
        ReferenceBoundaryDriver().manifest.to_json(),
        encoding="utf-8",
    )
    code = main(
        [
            "conformance",
            "verify",
            "--manifest",
            str(manifest_path),
            "--report",
            str(report_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "certified"


def test_spec_is_machine_readable(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["conformance", "spec"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["contract_version"] == "1.0"
    assert document["invariants"]["BC-01"] == "Atomic intent"


def test_missing_secret_canary_environment_fails_configuration(capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(
        [
            "conformance",
            "run",
            "--reference",
            "--secret-canary-env",
            "MERGEN_TEST_MISSING_CANARY",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "environment variable" in captured.err

from __future__ import annotations

import io
import json
import os
import threading
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from fastapi_mergen.cli.main import main
from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.models import ConformanceReport
from fastapi_mergen.testing import ReferenceBoundaryDriver


@dataclass(frozen=True, slots=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def run_cli(
    *arguments: str,
    environment: dict[str, str] | None = None,
    unset_environment: tuple[str, ...] = (),
) -> CliResult:
    env = os.environ.copy()
    if environment:
        env.update(environment)
    for name in unset_environment:
        env.pop(name, None)

    stdout = io.StringIO()
    stderr = io.StringIO()
    result: list[int] = []
    failure: list[BaseException] = []

    def target() -> None:
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result.append(main(arguments))
        except BaseException as exc:  # pragma: no cover - surfaced in parent thread
            failure.append(exc)

    with patch.dict(os.environ, env, clear=True):
        thread = threading.Thread(
            target=target,
            name="mergen-cli-test",
            daemon=True,
        )
        thread.start()
        thread.join(timeout=30)
    if thread.is_alive():
        raise AssertionError("CLI test exceeded its bounded timeout.")
    if failure:
        raise failure[0]
    if len(result) != 1:
        raise AssertionError("CLI test did not return one process-style exit code.")
    return CliResult(result[0], stdout.getvalue(), stderr.getvalue())


def test_reference_run_emits_verifiable_json() -> None:
    completed = run_cli(
        "conformance",
        "run",
        "--reference",
        "--profile",
        "complete",
        "--format",
        "json",
    )
    assert completed.returncode == 0, completed.stderr
    report = ConformanceReport.from_json(completed.stdout)
    assert report.certified
    assert not completed.stderr


def test_reference_fault_returns_nonzero() -> None:
    completed = run_cli(
        "conformance",
        "run",
        "--reference",
        "--profile",
        "complete",
        "--fault",
        "stale_lease_accepted",
    )
    report = ConformanceReport.from_json(completed.stdout)
    assert completed.returncode == 1
    assert not report.certified


def test_manifest_input_requires_no_driver_source(tmp_path: Path) -> None:
    manifest = ReferenceBoundaryDriver().manifest
    path = tmp_path / "manifest.json"
    path.write_text(manifest.to_json(), encoding="utf-8")
    completed = run_cli("conformance", "manifest", "--input", str(path))
    assert completed.returncode == 0, completed.stderr
    assert CapabilityManifest.from_json(completed.stdout) == manifest


def test_manifest_rejects_ambiguous_sources(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(ReferenceBoundaryDriver().manifest.to_json(), encoding="utf-8")
    completed = run_cli(
        "conformance",
        "manifest",
        "--input",
        str(path),
        "--reference",
    )
    assert completed.returncode == 2
    assert "exactly one" in completed.stderr


def test_adapter_factory_is_loaded_explicitly() -> None:
    completed = run_cli(
        "conformance",
        "run",
        "--adapter",
        "tests.conformance.fixtures:create_async_driver",
        "--profile",
        "core",
    )
    report = ConformanceReport.from_json(completed.stdout)
    assert completed.returncode == 0, completed.stderr
    assert report.certified


def test_verify_binds_report_to_manifest(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    manifest_path = tmp_path / "manifest.json"
    run = run_cli(
        "conformance",
        "run",
        "--reference",
        "--profile",
        "complete",
        "--output",
        str(report_path),
    )
    assert run.returncode == 0, run.stderr
    manifest_path.write_text(
        ReferenceBoundaryDriver().manifest.to_json(),
        encoding="utf-8",
    )
    completed = run_cli(
        "conformance",
        "verify",
        "--manifest",
        str(manifest_path),
        "--report",
        str(report_path),
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "certified"


def test_spec_is_machine_readable() -> None:
    completed = run_cli("conformance", "spec")
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    assert document["contract_version"] == "1.0"
    assert document["invariants"]["BC-01"] == "Atomic intent"
    assert document["invariants"]["BC-14"] == "External executor handoff"
    assert set(document["profiles"]) == {
        "core",
        "delivery",
        "security",
        "webhook",
        "executor",
        "command",
        "delegation",
        "complete",
    }


def test_missing_secret_canary_environment_fails_configuration() -> None:
    completed = run_cli(
        "conformance",
        "run",
        "--reference",
        "--secret-canary-env",
        "MERGEN_TEST_MISSING_CANARY",
        unset_environment=("MERGEN_TEST_MISSING_CANARY",),
    )
    assert completed.returncode == 2
    assert "environment variable" in completed.stderr


def test_adapter_factory_failure_is_bounded() -> None:
    completed = run_cli(
        "conformance",
        "run",
        "--adapter",
        "tests.conformance.fixtures:failing_factory",
        "--profile",
        "core",
    )
    assert completed.returncode == 2
    assert "could not be loaded" in completed.stderr
    assert "factory-secret-detail" not in completed.stderr

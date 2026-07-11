from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi_mergen.conformance.manifest import CapabilityManifest
from fastapi_mergen.conformance.models import ConformanceReport
from fastapi_mergen.testing import ReferenceBoundaryDriver

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"


def run_cli(
    *arguments: str,
    environment: dict[str, str] | None = None,
    unset_environment: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in tuple(env):
        if name == "PYTEST_CURRENT_TEST" or name.startswith(("COV_CORE_", "COVERAGE_")):
            env.pop(name, None)
    python_path = os.pathsep.join((str(SOURCE), str(ROOT)))
    env["PYTHONPATH"] = (
        python_path
        if not env.get("PYTHONPATH")
        else os.pathsep.join((python_path, env["PYTHONPATH"]))
    )
    if environment:
        env.update(environment)
    for name in unset_environment:
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, "-m", "fastapi_mergen", *arguments],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


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

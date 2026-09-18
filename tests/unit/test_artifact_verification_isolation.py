from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from scripts.build_and_test_artifacts import (
    ROOT,
    _runtime_node_id,
    assert_installed_package_origin,
    clean_python_environment,
)


def test_runtime_node_id_resolves_only_repository_test_files() -> None:
    value = _runtime_node_id(
        "tests/unit/test_webhook_signing.py::test_standard_webhooks_verifies_exact_body"
    )

    assert value == (
        str((ROOT / "tests/unit/test_webhook_signing.py").resolve())
        + "::test_standard_webhooks_verifies_exact_body"
    )


@pytest.mark.parametrize("value", ["../outside.py", "tests", "missing.py"])
def test_runtime_node_id_rejects_unsafe_or_missing_paths(value: str) -> None:
    with pytest.raises(ValueError, match="invalid"):
        _runtime_node_id(value)


def test_release_workflow_does_not_reinstall_candidates_into_project_environment() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "uv pip install --reinstall" not in workflow
    assert "--runtime-test" in workflow
    assert "--runtime-certification" in workflow
    assert "wheel-certification.json" in workflow
    assert "sdist-certification.json" in workflow
    assert "uv run --no-sync" in workflow
    assert "GITHUB_RUN_ATTEMPT" in workflow
    assert "actions: read" in workflow
    assert "artifact-lock-constraints.txt" in workflow
    assert "github.run_attempt" in workflow


def test_artifact_builds_use_the_lock_export_for_pep517_dependencies() -> None:
    source = (ROOT / "scripts/build_and_test_artifacts.py").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"build",' in source
    assert '"--build-constraints"' in source
    assert "build = [" in project
    assert '"setuptools>=82,<83"' in project


def test_runtime_harness_sanitizes_source_import_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/controlled/source-shadow")
    monkeypatch.setenv("PYTHONHOME", "/controlled/python-home")
    monkeypatch.setenv("VIRTUAL_ENV", "/controlled/editable-environment")

    environment = clean_python_environment()

    assert "PYTHONPATH" not in environment
    assert "PYTHONHOME" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert environment["PYTHONNOUSERSITE"] == "1"


def test_origin_check_rejects_a_sentinel_source_shadow(tmp_path: Path) -> None:
    package = tmp_path / "fastapi_mergen"
    package.mkdir()
    (package / "__init__.py").write_text("SENTINEL = True\n", encoding="utf-8")

    with pytest.raises(subprocess.CalledProcessError):
        assert_installed_package_origin(Path(sys.executable), Path(sys.prefix), tmp_path)


def test_origin_check_rejects_the_editable_project_environment(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        assert_installed_package_origin(Path(sys.executable), Path(sys.prefix), tmp_path)


def test_artifact_certification_rejects_source_origin_in_its_own_process(
    tmp_path: Path,
) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/generate_real_certification.py"),
        "--manifest",
        str(tmp_path / "manifest.json"),
        "--report",
        str(tmp_path / "report.json"),
        "--expected-package-prefix",
        str(tmp_path / "not-the-project-environment"),
        "--artifact-kind",
        "wheel",
        "--artifact-input-sha256",
        "a" * 64,
        "--artifact-installed-sha256",
        "b" * 64,
        "--lock-sha256",
        "c" * 64,
        "--constraints-sha256",
        "d" * 64,
    ]

    completed = subprocess.run(
        command,
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "outside the artifact environment" in completed.stderr


def test_taskiq_worker_rejects_subprocess_import_drift(
    tmp_path: Path,
) -> None:
    environment = clean_python_environment()
    environment["MERGEN_EXPECTED_PACKAGE_PREFIX"] = str(tmp_path / "not-the-project-environment")
    completed = subprocess.run(
        [sys.executable, "-c", "import fastapi_mergen.testing.taskiq_worker_fixture"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "outside the certified artifact environment" in completed.stderr

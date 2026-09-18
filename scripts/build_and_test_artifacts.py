#!/usr/bin/env python3
"""Build and smoke-test sdist and wheel in isolated virtual environments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import site
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OPTIONAL_MODULES = (
    "cryptography",
    "httpx",
    "standardwebhooks",
    "taskiq",
    "fastmcp",
    "opentelemetry",
    "opentelemetry.sdk",
)


def run(
    *command: str,
    cwd: Path = ROOT,
    clean_python: bool = False,
) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    environment = None
    if clean_python:
        environment = clean_python_environment()
    if command and Path(command[0]).name == "uv":
        environment = os.environ.copy() if environment is None else environment
        environment.setdefault(
            "UV_CACHE_DIR",
            str(Path(tempfile.gettempdir()) / "mergen-uv-cache"),
        )
    subprocess.run(command, cwd=cwd, check=True, env=environment)


def clean_python_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment.pop("VIRTUAL_ENV", None)
    environment["PIP_NO_INPUT"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def scripts_directory(environment: Path) -> Path:
    return environment / ("Scripts" if os.name == "nt" else "bin")


def python_in(environment: Path) -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    return scripts_directory(environment) / executable


def console_in(environment: Path) -> Path:
    executable = "fastapi-mergen.exe" if os.name == "nt" else "fastapi-mergen"
    return scripts_directory(environment) / executable


def create_environment(path: Path, *, parent_dependencies: bool = False) -> Path:
    venv.EnvBuilder(with_pip=True, clear=True).create(path)
    python = python_in(path)
    if parent_dependencies:
        if os.name == "nt":
            purelib = path / "Lib" / "site-packages"
        else:
            purelib = (
                path
                / "lib"
                / f"python{sys.version_info.major}.{sys.version_info.minor}"
                / "site-packages"
            )
        purelib.mkdir(parents=True, exist_ok=True)
        parent_paths = [entry for entry in site.getsitepackages() if Path(entry).is_dir()]
        (purelib / "offline-parent-dependencies.pth").write_text(
            "\n".join(parent_paths) + "\n",
            encoding="utf-8",
        )
    return python


def assert_uninstalled_import_fails(python: Path, empty_directory: Path) -> None:
    code = "import importlib.util; assert importlib.util.find_spec('fastapi_mergen') is None"
    run(str(python), "-c", code, cwd=empty_directory, clean_python=True)


def assert_installed_package_origin(python: Path, environment: Path, directory: Path) -> None:
    expected_prefix = repr(str(environment.resolve()))
    code = (
        "from pathlib import Path; import sys, fastapi_mergen; "
        "package = Path(fastapi_mergen.__file__).resolve(); "
        "prefix = Path(sys.prefix).resolve(); "
        f"assert prefix == Path({expected_prefix}).resolve(); "
        "assert package.is_relative_to(prefix), package"
    )
    run(str(python), "-c", code, cwd=directory, clean_python=True)


def export_locked_constraints(output: Path) -> None:
    if shutil.which("uv") is None:
        raise RuntimeError("Exact artifact runtime verification requires uv lock export.")
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        "uv",
        "export",
        "--locked",
        "--all-extras",
        "--no-default-groups",
        "--group",
        "test",
        "--group",
        "build",
        "--no-emit-project",
        "--no-hashes",
        "--no-annotate",
        "--no-header",
        "--output-file",
        str(output),
        cwd=ROOT,
        clean_python=True,
    )


def requirement_for(artifact: Path, extra: str | None) -> str:
    if extra:
        return f"fastapi-mergen[{extra}] @ {artifact.resolve().as_uri()}"
    return str(artifact.resolve())


def smoke_install(
    artifact: Path,
    extra: str | None,
    *,
    system_site_packages: bool,
    no_deps: bool,
) -> None:
    with tempfile.TemporaryDirectory(prefix="mergen-artifact-") as raw:
        root = Path(raw)
        environment = root / "venv"
        python = create_environment(environment, parent_dependencies=system_site_packages)
        if not system_site_packages:
            assert_uninstalled_import_fails(python, root)
        command = [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-cache-dir",
        ]
        if no_deps:
            command.extend(("--no-deps", "--ignore-installed"))
        command.append(requirement_for(artifact, extra))
        run(*command, cwd=root, clean_python=True)

        code = [
            "import importlib.metadata",
            "import importlib.util",
            "import sys",
            "from pathlib import Path",
            "import fastapi_mergen",
            "package_path = Path(fastapi_mergen.__file__).resolve()",
            "prefix_path = Path(sys.prefix).resolve()",
            "assert package_path.is_relative_to(prefix_path), package_path",
            "assert package_path.with_name('py.typed').is_file()",
            "spec_path = package_path.parent / 'conformance' / 'spec'",
            "assert (spec_path / 'boundary-contract-v1.json').is_file()",
            "assert (spec_path / 'manifest-v1.schema.json').is_file()",
            "assert (spec_path / 'report-v1.schema.json').is_file()",
            "assert not package_path.parents[1].joinpath('mergen').exists()",
            "metadata = importlib.metadata.metadata('fastapi-mergen')",
            "assert metadata['Name'] == 'fastapi-mergen'",
            "assert metadata['Author'] == 'mergen-institute'",
        ]
        if extra == "webhooks":
            code.append("import fastapi_mergen.webhooks")
        elif extra == "otel":
            code.append("import fastapi_mergen.observability")
        elif extra == "taskiq":
            code.extend(
                (
                    "import taskiq",
                    "import fastapi_mergen.executors.taskiq.adapter",
                )
            )
        elif extra == "fastmcp":
            code.extend(
                (
                    "import fastmcp",
                    "import fastapi_mergen.integrations.fastmcp",
                )
            )
        elif not no_deps:
            code.extend(
                (
                    f"optional_modules = {OPTIONAL_MODULES!r}",
                    "for module in optional_modules:\n"
                    "    try:\n"
                    "        available = importlib.util.find_spec(module) is not None\n"
                    "    except (ImportError, ModuleNotFoundError, ValueError):\n"
                    "        available = False\n"
                    "    assert not available, module",
                )
            )
        run(
            str(python),
            "-c",
            "\n".join(code),
            cwd=root,
            clean_python=True,
        )
        run(
            str(python),
            "-m",
            "fastapi_mergen",
            "--version",
            cwd=root,
            clean_python=True,
        )
        run(
            str(console_in(environment)),
            "conformance",
            "spec",
            cwd=root,
            clean_python=True,
        )
        if not no_deps:
            run(
                str(python),
                "-m",
                "pip",
                "check",
                cwd=root,
                clean_python=True,
            )


def runtime_test_install(
    artifact: Path,
    tests: tuple[str, ...],
    *,
    constraints_file: Path,
    lock_file: Path,
    certification_directory: Path | None = None,
) -> dict[str, object]:
    """Run selected journeys with the candidate as the only importable package."""

    artifact = artifact.resolve()
    with tempfile.TemporaryDirectory(prefix="mergen-artifact-runtime-") as raw:
        root = Path(raw)
        candidate = artifact.resolve()
        report: dict[str, object] = {
            "artifact_kind": "sdist" if artifact.name.endswith(".tar.gz") else "wheel",
            "input_path": artifact.relative_to(ROOT).as_posix(),
            "input_sha256": sha256_file(artifact),
            "tests": list(tests),
            "lock_sha256": sha256_file(lock_file),
            "constraints_path": constraints_file.relative_to(ROOT).as_posix(),
            "constraints_sha256": sha256_file(constraints_file),
        }
        if artifact.name.endswith(".tar.gz"):
            derived = root / "derived"
            derived.mkdir()
            if shutil.which("uv") is None:
                raise RuntimeError("Sdist runtime verification requires uv.")
            run(
                "uv",
                "build",
                "--wheel",
                "--clear",
                "--out-dir",
                str(derived),
                "--build-constraints",
                str(constraints_file),
                str(candidate),
                cwd=root,
                clean_python=True,
            )
            wheels = tuple(derived.glob("*.whl"))
            if len(wheels) != 1:
                raise AssertionError("sdist runtime verification produced an ambiguous wheel set")
            candidate = wheels[0]
            report["derived_wheel_sha256"] = sha256_file(candidate)

        environment = root / "runtime-venv"
        python = create_environment(environment)
        assert_uninstalled_import_fails(python, root)
        run(
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-cache-dir",
            "--constraint",
            str(constraints_file),
            "pytest>=9,<10",
            "pytest-asyncio>=1.3,<2",
            requirement_for(candidate, "webhooks,otel,taskiq,fastmcp"),
            cwd=root,
            clean_python=True,
        )
        assert_installed_package_origin(python, environment, root)
        run(
            str(python),
            "-m",
            "pytest",
            "-q",
            "--rootdir",
            str(ROOT),
            *(_runtime_node_id(value) for value in tests),
            cwd=root,
            clean_python=True,
        )
        report["installed_candidate_sha256"] = sha256_file(candidate)
        report["installed_from"] = (
            "sdist-derived-wheel" if artifact.name.endswith(".tar.gz") else "wheel"
        )
        report["package_origin_verified"] = True
        if certification_directory is not None:
            kind = str(report["artifact_kind"])
            certification_directory.mkdir(parents=True, exist_ok=True)
            manifest = certification_directory / f"{kind}-certification-manifest.json"
            certification_report = certification_directory / f"{kind}-certification.json"
            run(
                str(python),
                str(ROOT / "scripts" / "generate_real_certification.py"),
                "--manifest",
                str(manifest),
                "--report",
                str(certification_report),
                "--expected-package-prefix",
                str(environment),
                "--artifact-kind",
                kind,
                "--artifact-input-sha256",
                str(report["input_sha256"]),
                "--artifact-installed-sha256",
                str(report["installed_candidate_sha256"]),
                "--lock-sha256",
                str(report["lock_sha256"]),
                "--constraints-sha256",
                str(report["constraints_sha256"]),
                cwd=root,
                clean_python=True,
            )
            run(
                str(python),
                "-m",
                "fastapi_mergen",
                "conformance",
                "verify",
                "--manifest",
                str(manifest),
                "--report",
                str(certification_report),
                cwd=root,
                clean_python=True,
            )
            report["certification"] = {
                "manifest_path": manifest.relative_to(ROOT).as_posix(),
                "manifest_sha256": sha256_file(manifest),
                "report_path": certification_report.relative_to(ROOT).as_posix(),
                "report_sha256": sha256_file(certification_report),
            }
        report["status"] = "passed"
        return report


def _runtime_node_id(value: str) -> str:
    path, separator, selection = value.partition("::")
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT) or not resolved.is_file():
        raise ValueError(f"Artifact runtime test path is invalid: {path}")
    return str(resolved) + (separator + selection if separator else "")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    required = {
        "fastapi_mergen/py.typed",
        "fastapi_mergen/conformance/spec/boundary-contract-v1.json",
        "fastapi_mergen/conformance/spec/manifest-v1.schema.json",
        "fastapi_mergen/conformance/spec/report-v1.schema.json",
    }
    missing = required - names
    if missing:
        raise AssertionError(f"wheel is missing package data: {sorted(missing)}")
    if any(name.startswith("mergen/") for name in names):
        raise AssertionError("wheel contains the occupied top-level mergen package")
    if any("/.git/" in name or name.startswith(".git/") for name in names):
        raise AssertionError("wheel contains Git repository metadata")


def inspect_sdist(sdist: Path) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
    suffixes = (
        "/src/fastapi_mergen/py.typed",
        "/src/fastapi_mergen/conformance/spec/boundary-contract-v1.json",
        "/src/fastapi_mergen/conformance/spec/manifest-v1.schema.json",
        "/src/fastapi_mergen/conformance/spec/report-v1.schema.json",
        "/docs/tutorials/quickstart.md",
        "/examples/deployment/.env.example",
        "/tests/integration/test_invoicing_postgres_boot.py",
        "/examples/invoicing/relay.py",
        "/scripts/build_and_test_artifacts.py",
    )
    missing = [suffix for suffix in suffixes if not any(name.endswith(suffix) for name in names)]
    if missing:
        raise AssertionError(f"sdist is missing package data: {missing}")
    if any("/.git/" in name or name.endswith("/.git") for name in names):
        raise AssertionError("sdist contains Git repository metadata")


def build_with_available_backend(
    *,
    offline: bool,
    build_constraints: Path | None = None,
) -> None:
    if offline:
        if shutil.which("uv"):
            command = ["uv", "build", "--offline", "--no-sources"]
            if build_constraints is not None:
                command.extend(("--build-constraints", str(build_constraints)))
            run(*command)
            return
        run(
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(DIST),
        )
        run(
            sys.executable,
            "-c",
            "from setuptools.build_meta import build_sdist; build_sdist('dist')",
        )
        return
    if shutil.which("uv"):
        command = ["uv", "build", "--no-sources"]
        if build_constraints is not None:
            command.extend(("--build-constraints", str(build_constraints)))
        run(*command)
        return
    if build_constraints is not None:
        raise RuntimeError("Lock-constrained artifact builds require uv.")
    try:
        import build  # noqa: F401
    except ImportError:
        run(
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(DIST),
        )
        run(
            sys.executable,
            "-c",
            "from setuptools.build_meta import build_sdist; build_sdist('dist')",
        )
    else:
        run(sys.executable, "-m", "build")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--offline-system-packages",
        action="store_true",
        help="Use existing system packages and --no-deps for local offline smoke tests.",
    )
    parser.add_argument(
        "--runtime-test",
        action="append",
        default=[],
        help="Pytest node ID to run independently from the installed wheel and sdist.",
    )
    parser.add_argument(
        "--runtime-certification",
        action="store_true",
        help="Run complete real-service certification independently from each artifact.",
    )
    args = parser.parse_args()
    release_directory = ROOT / "build" / "release"
    constraints_file: Path | None = None
    lock_file = ROOT / "uv.lock"
    if args.runtime_test:
        constraints_file = release_directory / "artifact-lock-constraints.txt"
        export_locked_constraints(constraints_file)
    if not args.skip_build:
        shutil.rmtree(DIST, ignore_errors=True)
        DIST.mkdir(parents=True, exist_ok=True)
        build_with_available_backend(
            offline=args.offline_system_packages,
            build_constraints=constraints_file,
        )

    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise AssertionError("expected exactly one wheel and one sdist")
    wheel = wheels[0]
    sdist = sdists[0]
    inspect_wheel(wheel)
    inspect_sdist(sdist)

    offline = args.offline_system_packages
    smoke_install(wheel, None, system_site_packages=offline, no_deps=offline)
    if not offline:
        smoke_install(wheel, "webhooks", system_site_packages=False, no_deps=False)
        smoke_install(wheel, "otel", system_site_packages=False, no_deps=False)
        smoke_install(wheel, "taskiq", system_site_packages=False, no_deps=False)
        smoke_install(wheel, "fastmcp", system_site_packages=False, no_deps=False)
        smoke_install(sdist, None, system_site_packages=False, no_deps=False)
    if args.runtime_certification and not args.runtime_test:
        raise AssertionError("artifact certification requires at least one runtime journey")
    if args.runtime_test:
        assert constraints_file is not None
        reports = [
            runtime_test_install(
                artifact,
                tuple(args.runtime_test),
                constraints_file=constraints_file,
                lock_file=lock_file,
                certification_directory=release_directory if args.runtime_certification else None,
            )
            for artifact in (wheel, sdist)
        ]
        report_path = release_directory / "artifact-runtime-results.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {"schema_version": 1, "status": "passed", "artifacts": reports},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print("Clean artifact smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build and smoke-test sdist and wheel in isolated virtual environments."""

from __future__ import annotations

import argparse
import os
import shutil
import site
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def run(*command: str, cwd: Path = ROOT, clean_python: bool = False) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    environment = None
    if clean_python:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
    subprocess.run(command, cwd=cwd, check=True, env=environment)


def python_in(environment: Path) -> Path:
    scripts = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    return environment / scripts / executable


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
        ]
        if no_deps:
            command.extend(("--no-deps", "--ignore-installed"))
        command.append(requirement_for(artifact, extra))
        run(*command, cwd=root, clean_python=True)
        code = [
            "import fastapi_mergen",
            "from pathlib import Path",
            "assert Path(fastapi_mergen.__file__).with_name('py.typed').is_file()",
            "assert not Path(fastapi_mergen.__file__).parents[1].joinpath('mergen').exists()",
            "import sys",
            "package_path = str(Path(fastapi_mergen.__file__).resolve())",
            "prefix_path = str(Path(sys.prefix).resolve())",
            "assert package_path.startswith(prefix_path)",
        ]
        if extra == "webhooks":
            code.append("import fastapi_mergen.webhooks")
        elif extra == "otel":
            code.append("import fastapi_mergen.observability")
        elif not no_deps:
            code.extend(
                (
                    "import importlib.util",
                    "assert importlib.util.find_spec('standardwebhooks') is None",
                    "assert importlib.util.find_spec('opentelemetry') is None",
                )
            )
        run(str(python), "-c", ";".join(code), cwd=root, clean_python=True)
        if not no_deps:
            run(str(python), "-m", "pip", "check", cwd=root, clean_python=True)


def inspect_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    if "fastapi_mergen/py.typed" not in names:
        raise AssertionError("wheel does not contain fastapi_mergen/py.typed")
    if any(name.startswith("mergen/") for name in names):
        raise AssertionError("wheel contains the occupied top-level mergen package")


def build_with_available_backend(*, offline: bool) -> None:
    if offline:
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
        run("uv", "build", "--no-sources")
        return
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
    args = parser.parse_args()
    if not args.skip_build:
        shutil.rmtree(DIST, ignore_errors=True)
        DIST.mkdir(parents=True, exist_ok=True)
        build_with_available_backend(offline=args.offline_system_packages)

    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise AssertionError("expected exactly one wheel and one sdist")
    wheel = wheels[0]
    inspect_wheel(wheel)

    offline = args.offline_system_packages
    smoke_install(wheel, None, system_site_packages=offline, no_deps=offline)
    if not offline:
        smoke_install(wheel, "webhooks", system_site_packages=False, no_deps=False)
        smoke_install(wheel, "otel", system_site_packages=False, no_deps=False)
        smoke_install(sdists[0], None, system_site_packages=False, no_deps=False)
    print("Clean artifact smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build and smoke-test sdist and wheel in isolated virtual environments."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def run(*command: str, env: dict[str, str] | None = None) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def python_in(environment: Path) -> Path:
    scripts = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    return environment / scripts / executable


def create_environment(path: Path) -> Path:
    venv.EnvBuilder(with_pip=True, clear=True).create(path)
    return python_in(path)


def smoke_install(artifact: Path, extra: str | None) -> None:
    with tempfile.TemporaryDirectory(prefix="mergen-artifact-") as raw:
        environment = Path(raw) / "venv"
        python = create_environment(environment)
        target = f"{artifact}[{extra}]" if extra else str(artifact)
        run(str(python), "-m", "pip", "install", "--disable-pip-version-check", target)
        code = [
            "import fastapi_mergen",
            "from pathlib import Path",
            "assert Path(fastapi_mergen.__file__).with_name('py.typed').is_file()",
            "assert not Path(fastapi_mergen.__file__).parents[1].joinpath('mergen').exists()",
        ]
        if extra == "webhooks":
            code.append("import fastapi_mergen.webhooks")
        elif extra == "otel":
            code.append("import fastapi_mergen.observability")
        else:
            code.extend(
                [
                    "import importlib.util",
                    "assert importlib.util.find_spec('standardwebhooks') is None",
                    "assert importlib.util.find_spec('opentelemetry') is None",
                ]
            )
        run(str(python), "-c", ";".join(code))
        run(str(python), "-m", "pip", "check")


def inspect_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    if "fastapi_mergen/py.typed" not in names:
        raise AssertionError("wheel does not contain fastapi_mergen/py.typed")
    if any(name.startswith("mergen/") for name in names):
        raise AssertionError("wheel contains the occupied top-level mergen package")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if not args.skip_build:
        shutil.rmtree(DIST, ignore_errors=True)
        run(sys.executable, "-m", "build")

    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise AssertionError("expected exactly one wheel and one sdist")
    wheel = wheels[0]
    inspect_wheel(wheel)
    smoke_install(wheel, None)
    smoke_install(wheel, "webhooks")
    smoke_install(wheel, "otel")
    smoke_install(sdists[0], None)
    print("Clean artifact smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

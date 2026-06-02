from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.packaging
def test_local_offline_wheel_smoke() -> None:
    """Exercise wheel build/import using already installed dependencies.

    CI runs the stronger networked matrix for truly clean base, webhook, OTel, and
    sdist environments. This local test still proves that imports come from the built
    wheel rather than the checkout.
    """
    subprocess.run(
        [
            sys.executable,
            "scripts/build_and_test_artifacts.py",
            "--offline-system-packages",
        ],
        cwd=ROOT,
        check=True,
    )

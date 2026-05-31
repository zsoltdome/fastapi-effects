from __future__ import annotations

import importlib.metadata
from pathlib import Path

from packaging.specifiers import SpecifierSet

import fastapi_mergen


def test_distribution_identity() -> None:
    metadata = importlib.metadata.metadata("fastapi-mergen")
    assert metadata["Name"] == "fastapi-mergen"
    assert metadata["Author"] == "mergen-institute"
    assert SpecifierSet(metadata["Requires-Python"] or "") == SpecifierSet(">=3.11,<3.15")
    assert fastapi_mergen.__version__ == importlib.metadata.version("fastapi-mergen")


def test_typed_marker_is_installed() -> None:
    package = Path(fastapi_mergen.__file__).parent
    assert (package / "py.typed").is_file()


def test_generic_mergen_package_is_absent() -> None:
    assert not (Path(fastapi_mergen.__file__).parent.parent / "mergen").exists()

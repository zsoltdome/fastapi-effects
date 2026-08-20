from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet

import fastapi_mergen

pytestmark = pytest.mark.packaging


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


def test_conformance_specs_are_installed() -> None:
    package = Path(fastapi_mergen.__file__).parent
    specification = package / "conformance" / "spec"
    assert (specification / "boundary-contract-v1.json").is_file()
    assert (specification / "manifest-v1.schema.json").is_file()
    assert (specification / "report-v1.schema.json").is_file()

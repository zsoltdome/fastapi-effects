from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet

import fastapi_effects

pytestmark = pytest.mark.packaging


def test_distribution_identity() -> None:
    metadata = importlib.metadata.metadata("fastapi-effects")
    assert metadata["Name"] == "fastapi-effects"
    assert metadata["Author"] == "Zsolt Döme"
    assert SpecifierSet(metadata["Requires-Python"] or "") == SpecifierSet(">=3.11,<3.15")
    assert fastapi_effects.__version__ == importlib.metadata.version("fastapi-effects")


def test_typed_marker_is_installed() -> None:
    package = Path(fastapi_effects.__file__).parent
    assert (package / "py.typed").is_file()


def test_conformance_specs_are_installed() -> None:
    package = Path(fastapi_effects.__file__).parent
    specification = package / "conformance" / "spec"
    assert (specification / "boundary-contract-v1.json").is_file()
    assert (specification / "manifest-v1.schema.json").is_file()
    assert (specification / "report-v1.schema.json").is_file()

"""Explicit driver loading for the conformance CLI."""

from __future__ import annotations

import importlib
import inspect
import re
from typing import Any

from fastapi_mergen.conformance.protocols import BoundaryDriver
from fastapi_mergen.errors import MergenConfigurationError

_DRIVER_SPEC = re.compile(
    r"^(?P<module>[A-Za-z_][A-Za-z0-9_.]*):(?P<attribute>[A-Za-z_][A-Za-z0-9_.]*)$"
)


async def load_driver(specification: str) -> BoundaryDriver:
    """Load a trusted application factory from ``module:attribute``.

    Loading imports and executes application code.  The CLI therefore treats the
    specification as a trusted deployment configuration, never as tenant input.
    """

    match = _DRIVER_SPEC.fullmatch(specification)
    if match is None or "__" in specification:
        raise MergenConfigurationError("Conformance driver specification is invalid.")
    try:
        value: Any = importlib.import_module(match.group("module"))
        for component in match.group("attribute").split("."):
            value = getattr(value, component)
        if callable(value) and not isinstance(value, BoundaryDriver):
            value = value()
        if inspect.isawaitable(value):
            value = await value
    except (ImportError, AttributeError, TypeError) as exc:
        raise MergenConfigurationError("Conformance driver could not be loaded.") from exc
    if not isinstance(value, BoundaryDriver):
        raise MergenConfigurationError("Loaded object is not a BoundaryDriver.")
    return value

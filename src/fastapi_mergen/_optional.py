"""Helpers for explicit optional-dependency boundaries."""

from __future__ import annotations

from importlib.util import find_spec

from fastapi_mergen.errors import OptionalDependencyError


def require_modules(*, feature: str, extra: str, modules: tuple[str, ...]) -> None:
    """Fail with an actionable message when an optional module is unavailable."""
    missing = tuple(module for module in modules if find_spec(module) is None)
    if missing:
        raise OptionalDependencyError(feature=feature, extra=extra, missing=missing)

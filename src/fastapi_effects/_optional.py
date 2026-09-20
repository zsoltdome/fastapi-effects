"""Helpers for explicit optional-dependency boundaries."""

from __future__ import annotations

from importlib.util import find_spec

from fastapi_effects.errors import OptionalDependencyError


def _module_is_available(module: str) -> bool:
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def require_modules(*, feature: str, extra: str, modules: tuple[str, ...]) -> None:
    """Fail with an actionable message when an optional module is unavailable."""
    missing = tuple(module for module in modules if not _module_is_available(module))
    if missing:
        raise OptionalDependencyError(feature=feature, extra=extra, missing=missing)

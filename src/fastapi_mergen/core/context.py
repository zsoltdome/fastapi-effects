"""Leak-safe process-local principal binding."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from fastapi_mergen.core.principal import Principal
from fastapi_mergen.errors import MergenConfigurationError

_principal: ContextVar[Principal | None] = ContextVar("fastapi_mergen_principal", default=None)


def bind_principal(principal: Principal) -> Token[Principal | None]:
    if not isinstance(principal, Principal):
        raise MergenConfigurationError("Only a validated Principal can be bound.")
    return _principal.set(principal)


def reset_principal(token: Token[Principal | None]) -> None:
    _principal.reset(token)


def current_principal(*, required: bool = True) -> Principal | None:
    principal = _principal.get()
    if principal is None and required:
        raise MergenConfigurationError("No Mergen principal is bound to this context.")
    return principal


@contextmanager
def principal_context(principal: Principal) -> Iterator[Principal]:
    token = bind_principal(principal)
    try:
        yield principal
    finally:
        reset_principal(token)


__all__ = ["bind_principal", "current_principal", "principal_context", "reset_principal"]

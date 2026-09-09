"""Reviewed classification for database failures at retryable control boundaries."""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

_TRANSIENT_SQLSTATES = frozenset(
    {
        "40001",  # serialization failure
        "40P01",  # deadlock detected
        "55P03",  # lock not available / lock timeout policy
        "57014",  # query cancelled, including statement timeout
        "57P01",  # admin shutdown
        "57P02",  # crash shutdown
        "57P03",  # cannot connect now
    }
)


def is_transient_database_error(error: BaseException) -> bool:
    """Return whether a failed short control operation may be retried later.

    The classifier is deliberately narrower than ``DBAPIError``. Invalidated
    connections and reviewed connection/transaction SQLSTATEs are transient;
    schema, permission, integrity, and programming failures remain visible.
    """

    if not isinstance(error, DBAPIError):
        return False
    if error.connection_invalidated:
        return True
    sqlstate = _sqlstate(error.orig)
    if sqlstate is not None:
        return sqlstate.startswith("08") or sqlstate in _TRANSIENT_SQLSTATES
    # Some async drivers do not expose a SQLSTATE once the transport is gone.
    return isinstance(error, (OperationalError, InterfaceError))


def _sqlstate(error: BaseException | None) -> str | None:
    for name in ("sqlstate", "pgcode"):
        value = getattr(error, name, None)
        if isinstance(value, str) and len(value) == 5:
            return value.upper()
    return None


__all__ = ["is_transient_database_error"]

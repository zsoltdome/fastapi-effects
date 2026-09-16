from __future__ import annotations

import errno
import socket

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from fastapi_mergen.postgres.errors import (
    is_transient_database_connection_error,
    is_transient_database_error,
)


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError(errno.ECONNREFUSED, "controlled"),
        ConnectionResetError(errno.ECONNRESET, "controlled"),
        TimeoutError(errno.ETIMEDOUT, "controlled"),
        socket.gaierror(socket.EAI_AGAIN, "controlled"),
        OperationalError("controlled", {}, RuntimeError("driver unavailable")),
        DBAPIError(
            "controlled",
            {},
            RuntimeError("connection invalidated"),
            connection_invalidated=True,
        ),
    ],
)
def test_connection_boundary_accepts_reviewed_transient_failures(error: BaseException) -> None:
    assert is_transient_database_connection_error(error)


@pytest.mark.parametrize(
    "error",
    [
        PermissionError(errno.EACCES, "controlled"),
        FileNotFoundError(errno.ENOENT, "controlled"),
        socket.gaierror(socket.EAI_NONAME, "controlled"),
        ProgrammingError("controlled", {}, RuntimeError("undefined table")),
        ValueError("invalid DSN"),
    ],
)
def test_connection_boundary_rejects_permanent_or_unrelated_failures(
    error: BaseException,
) -> None:
    assert not is_transient_database_connection_error(error)


def test_general_classifier_does_not_accept_raw_operating_system_errors() -> None:
    assert not is_transient_database_error(ConnectionRefusedError(errno.ECONNREFUSED, "controlled"))

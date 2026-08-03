"""Safety guards shared by explicit Alembic downgrades."""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import Connection, text

from fastapi_mergen.sqlalchemy.models import SCHEMA

_TABLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def reject_nonempty_downgrade(connection: Connection, tables: Sequence[str]) -> None:
    """Reject a destructive downgrade when any component table contains data."""

    for table in tables:
        if _TABLE.fullmatch(table) is None:
            raise RuntimeError("Unsafe migration table name.")
        exists = connection.scalar(
            text(
                "SELECT CASE WHEN to_regclass(:qualified) IS NULL THEN false "
                f"ELSE EXISTS (SELECT 1 FROM {SCHEMA}.{table} LIMIT 1) END"
            ),
            {"qualified": f"{SCHEMA}.{table}"},
        )
        if exists:
            raise RuntimeError(
                f"Refusing destructive downgrade: {SCHEMA}.{table} contains data. "
                "Archive, restore into a separate database, and validate before retrying."
            )


__all__ = ["reject_nonempty_downgrade"]

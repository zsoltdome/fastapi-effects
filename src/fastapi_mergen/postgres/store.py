"""PostgreSQL store declaration for the Milestone 1 API contract."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi_mergen.errors import MergenConfigurationError, MilestoneNotImplementedError

_SCHEMA_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


@dataclass(frozen=True, slots=True)
class PostgresStore:
    """Fail-closed placeholder for the Milestone 2 PostgreSQL effect store.

    The class freezes configuration ergonomics without implying that schema,
    RLS, event persistence, or relay behavior exists in version 0.0.1.
    """

    schema: str = "fastapi_mergen"

    def __post_init__(self) -> None:
        if not isinstance(self.schema, str) or not _SCHEMA_NAME_PATTERN.fullmatch(self.schema):
            raise MergenConfigurationError("PostgreSQL schema name is invalid.")

    @property
    def name(self) -> str:
        """Return the stable store identifier used by diagnostics."""

        return "postgresql"

    def require_implementation(self) -> None:
        """Fail before any caller can mistake the API declaration for persistence."""

        raise MilestoneNotImplementedError(
            "PostgreSQL effect persistence is frozen but not implemented until Milestone 2."
        )

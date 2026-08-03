"""Frozen v1 PostgreSQL component-revision registry and compatibility gate."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi_mergen.errors import MergenConfigurationError, SchemaRevisionMismatch
from fastapi_mergen.sqlalchemy.models import SCHEMA

MIGRATION_HEAD = "0005_webhook_retention"


@dataclass(frozen=True, slots=True)
class SchemaComponent:
    """One independently checked schema-bearing capability."""

    name: str
    revision: int
    introduced_by: str


SCHEMA_COMPONENTS = (
    SchemaComponent("core", 1, "0001_core_runtime"),
    SchemaComponent("webhooks", 2, "0005_webhook_retention"),
    SchemaComponent("executor.taskiq", 1, "0003_taskiq"),
    SchemaComponent("commands", 1, "0004_commands"),
)
SCHEMA_REVISION_REGISTRY: Mapping[str, int] = MappingProxyType(
    {component.name: component.revision for component in SCHEMA_COMPONENTS}
)


async def read_schema_revisions(engine: AsyncEngine) -> Mapping[str, int]:
    """Read installed revisions without changing the database."""

    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(f"SELECT component, revision FROM {SCHEMA}.schema_revision")
                )
            ).all()
    except SQLAlchemyError as exc:
        raise SchemaRevisionMismatch(component="core", expected=1, actual=0) from exc
    return MappingProxyType({str(row.component): int(row.revision) for row in rows})


async def check_schema_revisions(
    engine: AsyncEngine,
    *,
    components: Iterable[str] | None = None,
) -> None:
    """Reject missing, older, and newer revisions; never migrate implicitly."""

    requested = tuple(SCHEMA_REVISION_REGISTRY if components is None else components)
    unknown = tuple(name for name in requested if name not in SCHEMA_REVISION_REGISTRY)
    if unknown:
        raise MergenConfigurationError(f"Unknown schema component: {unknown[0]!r}.")
    actual = await read_schema_revisions(engine)
    for component in requested:
        expected_revision = SCHEMA_REVISION_REGISTRY[component]
        actual_revision = actual.get(component, 0)
        if actual_revision != expected_revision:
            raise SchemaRevisionMismatch(
                component=component,
                expected=expected_revision,
                actual=actual_revision,
            )


__all__ = [
    "MIGRATION_HEAD",
    "SCHEMA_COMPONENTS",
    "SCHEMA_REVISION_REGISTRY",
    "SchemaComponent",
    "check_schema_revisions",
    "read_schema_revisions",
]

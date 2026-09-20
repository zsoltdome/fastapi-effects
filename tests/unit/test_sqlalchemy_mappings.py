from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint

from fastapi_effects.sqlalchemy.models import SCHEMA, Base


def test_runtime_metadata_uses_authoritative_schema_and_tenant_foreign_keys() -> None:
    tables = Base.metadata.tables
    assert {
        f"{SCHEMA}.schema_revision",
        f"{SCHEMA}.events",
        f"{SCHEMA}.deliveries",
        f"{SCHEMA}.attempts",
    }.issubset(tables)
    for name in ("events", "deliveries", "attempts"):
        assert "tenant_id" in tables[f"{SCHEMA}.{name}"].c
    foreign_keys = [
        constraint
        for constraint in tables[f"{SCHEMA}.deliveries"].constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    assert any(
        {column.name for column in constraint.columns} == {"tenant_id", "event_id"}
        for constraint in foreign_keys
    )

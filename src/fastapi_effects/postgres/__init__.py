"""PostgreSQL integration surface."""

from fastapi_effects.postgres.leasing import ClaimedDelivery
from fastapi_effects.postgres.relay import DeliverySink, PollingRelay, RelayConfig, SinkDisposition
from fastapi_effects.postgres.revisions import (
    MIGRATION_HEAD,
    SCHEMA_REVISION_REGISTRY,
    check_schema_revisions,
)
from fastapi_effects.postgres.roles import RuntimeRoles
from fastapi_effects.postgres.schema import check_core_schema, install_core_schema
from fastapi_effects.postgres.store import PostgresStore

__all__ = [
    "MIGRATION_HEAD",
    "SCHEMA_REVISION_REGISTRY",
    "ClaimedDelivery",
    "DeliverySink",
    "PollingRelay",
    "PostgresStore",
    "RelayConfig",
    "RuntimeRoles",
    "SinkDisposition",
    "check_core_schema",
    "check_schema_revisions",
    "install_core_schema",
]

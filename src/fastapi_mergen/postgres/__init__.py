"""PostgreSQL integration surface."""

from fastapi_mergen.postgres.leasing import ClaimedDelivery
from fastapi_mergen.postgres.relay import DeliverySink, PollingRelay, RelayConfig, SinkDisposition
from fastapi_mergen.postgres.revisions import (
    MIGRATION_HEAD,
    SCHEMA_REVISION_REGISTRY,
    check_schema_revisions,
)
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import check_core_schema, install_core_schema
from fastapi_mergen.postgres.store import PostgresStore

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

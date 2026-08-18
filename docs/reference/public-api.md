# Public API and compatibility status

This page is the v1 compatibility inventory. A symbol is contractual only when it is
listed here or exported by one of the listed namespace `__all__` values. Everything
else under `fastapi_mergen` is internal, even when Python can import it.

## Stable root surface

The following typed imports are stable for the v1 line:

| Category | Symbols |
| --- | --- |
| Runtime | `Mergen`, `MergenUnitOfWork`, `EffectContext`, `Event`, `Principal`, `RetryPolicy`, `AuthorizationMode` |
| Base/configuration | `MergenError`, `MergenConfigurationError`, `OptionalDependencyError` |
| Authorization | `AuthenticationRequired`, `AuthorizationDenied`, `AuthorizationExpired` |
| Concurrency/identity | `DedupeConflict`, `OptimisticConflict`, `CommandConflict`, `CommandInProgress`, `LeaseLost` |
| Delivery/schema | `RetryableDeliveryError`, `PermanentDeliveryError`, `SchemaRevisionMismatch` |
| Metadata | `__version__` |

`MilestoneNotImplementedError` remains importable for compatibility but is deprecated.
It will not be raised by the production runtime and may be removed in v2.

Every `MergenError` class has a stable, low-cardinality `error_code`. Delivery
classification supplied by an application remains in the separate instance `code`
field of `RetryableDeliveryError` and `PermanentDeliveryError`. Exception messages,
summaries, and reprs are not machine contracts and must not be used for branching.

## Stable integration namespaces

The exports in these namespace `__all__` values are stable and import-tested:

- `fastapi_mergen.postgres`: store and explicit schema compatibility gate;
- `fastapi_mergen.sqlalchemy`: UoW and extension types;
- `fastapi_mergen.idempotency`: command-boundary values and request preparation;
- `fastapi_mergen.delegation`: claims, key lifecycle, signing, verification;
- `fastapi_mergen.executors`: durable handoff protocols;
- `fastapi_mergen.observability`: bounded event/sink protocol;
- `fastapi_mergen.conformance` and `fastapi_mergen.testing`: contract and adapter
  certification APIs.

Integration implementation modules such as `webhooks.*`, `executors.taskiq.*`,
`delegation.fastapi`, and `integrations.fastmcp` are supported through their documented
examples but remain provisional in the first v1 line. Their persisted data, security
invariants, CLI behavior, and conformance profiles are contractual; their Python helper
signatures may receive compatible refinements before they are promoted to a namespace
surface.

## Non-contractual internals

ORM rows, repositories, migration implementation helpers, private names, and any module
not listed above are implementation details. In particular, no SQLAlchemy expression,
DBAPI connection, HTTP client, broker object, or relay-control session is public.
Database tables must be accessed through documented operations rather than treated as a
public ORM API.

## CLI and environment

Stable command paths are `doctor`, `schema check`, `relay run`, `webhooks
validate-endpoint`, `commands prune`, and `conformance` (`run`, `manifest`, `verify`,
`spec`). Existing options keep their meaning for the v1 line. New options and commands
may be added compatibly.

`MERGEN_DATABASE_DSN` is the only library CLI environment variable. Command-line
`--dsn` takes precedence. `MERGEN_TEST_ADMIN_DSN`, `MERGEN_EXAMPLE_DATABASE_URL`, and
`WEBHOOK_SIGNING_SECRET` belong to tests or examples and are not library configuration.
Secrets and DSNs are never emitted in diagnostic output.

## Deprecation policy

Breaking Python, CLI, environment, evidence-schema, or database-contract changes require:

1. a changelog entry and a runtime warning where one can be emitted safely;
2. a supported replacement and migration instructions;
3. at least one full minor release and 90 days of warning, whichever is longer;
4. removal only in the next major version, except for a documented critical security
   issue where continued support would be unsafe.

Adding optional parameters, fields with defaults, enum members whose consumers are
required to handle unknown values, or new CLI subcommands is compatible. Changing a
stable error code, deleting a report field, silently migrating a database, or narrowing
accepted input is breaking.

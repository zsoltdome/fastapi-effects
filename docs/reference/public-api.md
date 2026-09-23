# Public API and compatibility status

This page is the v1 compatibility inventory and the alpha maturity map. A symbol is a
documented v1 target only when it is listed here or exported by one of the listed
namespace `__all__` values. The current alpha classification is governed by
[ADR-017](../adr/ADR-017-quarter-release-scope.md); “v1 target” does not imply that a
`0.x` alpha helper is already frozen. Everything else under `fastapi_effects` is
internal, even when Python can import it.

## Stable-target root surface

The following typed imports are the quarter's stable target and the committed v1 root
surface:

| Category | Symbols |
| --- | --- |
| Runtime | `FastAPIEffects`, `FastAPIEffectsUnitOfWork`, `EffectContext`, `Event`, `Principal`, `RetryPolicy`, `AuthorizationMode` |
| Base/configuration | `FastAPIEffectsError`, `FastAPIEffectsConfigurationError`, `OptionalDependencyError` |
| Authorization | `AuthenticationRequired`, `AuthorizationDenied`, `AuthorizationExpired` |
| Concurrency/identity | `DedupeConflict`, `OptimisticConflict`, `CommandConflict`, `CommandInProgress`, `LeaseLost` |
| Delivery/schema | `RetryableDeliveryError`, `PermanentDeliveryError`, `SchemaRevisionMismatch` |
| Metadata | `__version__` |

`MilestoneNotImplementedError` remains importable for compatibility but is deprecated.
It will not be raised by the production runtime and may be removed in v2.

Every `FastAPIEffectsError` class has a stable, low-cardinality `error_code`. Delivery
classification supplied by an application remains in the separate instance `code`
field of `RetryableDeliveryError` and `PermanentDeliveryError`. Exception messages,
summaries, and reprs are not machine contracts and must not be used for branching.

## Namespace maturity

The exports in these namespace `__all__` values are documented and import-tested:

- `fastapi_effects.postgres`: store, explicit schema compatibility/install gates,
  runtime roles, and polling relay/sink composition;
- `fastapi_effects.sqlalchemy`: UoW and extension types;
- `fastapi_effects.idempotency`: command-boundary values and request preparation;
- `fastapi_effects.delegation`: claims, key lifecycle, signing, verification;
- `fastapi_effects.executors`: durable handoff protocols;
- `fastapi_effects.observability`: bounded event/sink protocol;
- `fastapi_effects.conformance` and `fastapi_effects.testing`: contract and adapter
  certification APIs.

The PostgreSQL and SQLAlchemy entries above are the narrow stable target. The supported
PostgreSQL composition symbols are `PostgresStore`, `PollingRelay`,
`RelayConfig`, `DeliverySink`, `SinkDisposition`, `ClaimedDelivery`, `RuntimeRoles`,
`install_core_schema`, `check_core_schema`, `check_schema_revisions`, `MIGRATION_HEAD`,
and `SCHEMA_REVISION_REGISTRY`.

The `idempotency`, `delegation`, `executors`, `observability`, `conformance`, and
`testing` namespace exports remain documented v1 targets, but their optional helper
APIs are provisional during this alpha and are outside the quarter's narrow freeze.
Integration implementation modules such as `webhooks.*`, `executors.taskiq.*`,
`delegation.fastapi`, and `integrations.fastmcp` are likewise provisional. Their
persisted data, security invariants, CLI behavior, versioned evidence formats, and
conformance profiles are contractual; helper signatures may receive compatible
refinements before promotion. Existing commitments cannot be removed without the
deprecation policy.

## Non-contractual internals

ORM rows, repositories, migration implementation helpers, private names, and any module
not listed above are implementation details. In particular, no SQLAlchemy expression,
DBAPI connection, HTTP client, broker object, or relay-control session is public.
Database tables must be accessed through documented operations rather than treated as a
public ORM API.

## CLI and environment

Stable command paths are `doctor`, `schema check`, `schema upgrade`, `relay run`, `webhooks
validate-endpoint`, `commands prune`, and `conformance` (`run`, `manifest`, `verify`,
`spec`). Existing options keep their meaning for the v1 line. New options and commands
may be added compatibly.

`FASTAPI_EFFECTS_DATABASE_DSN` is the only library CLI environment variable. Command-line
`--dsn` takes precedence. `FASTAPI_EFFECTS_TEST_ADMIN_DSN`, `FASTAPI_EFFECTS_EXAMPLE_DATABASE_URL`, and
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

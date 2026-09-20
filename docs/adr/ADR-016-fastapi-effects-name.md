# ADR-016: Adopt the FastAPI Effects name

- **Status:** Accepted
- **Date:** 2026-09-20

## Decision

The public product name is **FastAPI Effects**, with the description “Durable,
tenant-aware side effects for FastAPI and PostgreSQL.” The Python distribution and
console command are `fastapi-effects`. The import root, PostgreSQL schema and roles,
transaction-local settings, telemetry keys, environment variables, error codes,
canonical serialization prefixes, advisory-lock keys, and versioned conformance
identifiers use `fastapi_effects`. Public Python types use the `FastAPIEffects` prefix
where a brand-qualified name is needed.

No compatibility import package or command alias is shipped. This is an intentional
breaking change to a pre-v1 alpha surface, made before downstream compatibility is
promised. Existing development databases must be recreated or migrated explicitly;
the package never silently renames database objects or rewrites stored identities.

Package metadata and copyright attribution name Zsolt Döme as the author. Public
repository metadata targets `zsoltdome/fastapi-effects`.

## Consequences

- New installations use `pip install fastapi-effects`.
- Documentation and examples use `fastapi-effects` and `fastapi_effects` consistently.
- Pre-release automation, imports, database objects, metrics, stored identities, and
  signed or hashed canonical values require an explicit migration.
- Future changes to these deployed or durable names require an independent migration
  and deprecation decision.

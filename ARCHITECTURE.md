# Architecture

FastAPI Effects is an async Python package for committing application state and durable
effect intent in one PostgreSQL transaction, then delivering those effects outside the
transaction without losing tenant or authority provenance.

This document is the short component map. The
[Boundary Contract](docs/concepts/boundary-contract.md),
[public API inventory](docs/reference/public-api.md), and
[architecture decisions](docs/adr/README.md) are the detailed sources of truth.

## Runtime flow

1. FastAPI authentication constructs a tenant-bound `Principal`.
2. `FastAPIEffectsUnitOfWork` opens a caller-owned async SQLAlchemy transaction.
3. Application changes, events, immutable routes, and original deliveries commit
   atomically.
4. `PollingRelay` claims deliveries with fenced leases and commits before any handler,
   broker, or network I/O.
5. A fresh tenant-bound session restores the recorded authority mode and executes the
   selected sink.
6. Finalization records the attempt outcome only when the lease token is still current.
7. Automatic retry preserves the delivery identity; manual replay creates a new linked
   identity.

## Component map

| Area | Responsibility |
|---|---|
| `fastapi_effects.core` | Principal, event, route, delivery, retry, and authorization contracts |
| `fastapi_effects.sqlalchemy` | Explicit unit-of-work integration and atomic effect persistence |
| `fastapi_effects.postgres` | PostgreSQL stores, migrations, RLS, leases, relay, and schema gates |
| `fastapi_effects.handlers` | In-process delivery with fresh application sessions |
| `fastapi_effects.webhooks` | Signed delivery, encrypted secrets, endpoint policy, and replay controls |
| `fastapi_effects.executors` | Durable external handoff contracts, including Taskiq |
| `fastapi_effects.idempotency` | Transactional inbound-command deduplication and response replay |
| `fastapi_effects.delegation` | Audience-bound delegated authority and key lifecycle |
| `fastapi_effects.observability` | Bounded, low-cardinality operational events |
| `fastapi_effects.conformance` | Executable Boundary Contract profiles and evidence formats |
| `fastapi_effects.testing` | Reference and real-adapter certification helpers |

## Enforced boundaries

- The application owns transaction entry, commit, and rollback.
- No handler or network I/O occurs while claim locks are held.
- Every delivery attempt uses a fresh session and re-establishes tenant context.
- Persisted routes contain data and policy identifiers, never Python callables or raw
  credentials.
- Tenant isolation is enforced by PostgreSQL roles and forced row-level security, not
  only by application filters.
- Delivery is at least once. Effectively-once business behavior requires consumer-side
  durable deduplication.
- Public compatibility applies only to documented exports, CLI paths, schemas, and
  database contracts.

The accepted decisions for transaction ownership, delivery identities, routing,
leases, roles, replay, delegation, and retention live under `docs/adr/`.

## Evidence and release path

Tests are separated into unit, integration, conformance, migration, packaging,
operations, security, and chaos evidence. `scripts/check.py` is the complete local
quality gate. GitHub Actions adds the Python/PostgreSQL matrix, dependency boundary
checks, security scans, and real-runtime certification.

Release workflows build the wheel and source distribution once, smoke-test those exact
artifacts, bind checksums and provenance, and promote the same artifacts through PyPI
Trusted Publishing. See [certification operations](docs/operations/certification.md).

## Deliberate non-goals

FastAPI Effects is not an authentication server, tenant manager, general workflow
engine, scheduler, queue service, synchronous SQLAlchemy layer, or database-agnostic
outbox. PostgreSQL and async SQLAlchemy are intentional parts of the contract.

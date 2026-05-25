# FastAPI-Mergen — Detailed Technical TODO for Milestones 1–3

**Date:** 2026-08-24  
**Companion plan:** `fastapi_mergen_plan_9x9_FINAL_2026-08-24.md`  
**Planning assumption:** solo, part-time, approximately 10 hours/week  
**Scope:** Milestone 1 repository/specification; Milestone 2 core engine; Milestone 3 webhook MDP

## How to use this checklist

- Complete tasks in dependency order unless the task explicitly permits parallel work.
- Check the task heading only after every nested Definition of Done checkbox is complete.
- A task is not complete when code merely works locally; documentation, tests, migration behavior, packaging, and security conditions in its DoD are part of the task.
- Any design change that alters a frozen invariant requires an ADR update and a re-estimate of downstream tasks.
- File paths are the intended repository locations; create missing parent packages with explicit `__init__.py` only where required by the selected namespace strategy.

## Cross-milestone non-negotiable rules

- [ ] No generic exactly-once claim: local publication is atomic; delivery is at least once.
- [ ] No handler or network I/O while database claim locks are held.
- [ ] No raw bearer token, cookie, API key, session token, or plaintext webhook secret in event/delivery/attempt rows or default logs.
- [ ] No runtime table ownership, superuser role, or `BYPASSRLS`.
- [ ] Relay control-plane sessions never enter application handler code.
- [ ] Automatic retry keeps the delivery/message ID; manual replay creates a new linked delivery.
- [ ] Polling remains the correctness mechanism through Milestone 3.
- [ ] No queue, MCP, workflow, ordering, cancellation, inbound-idempotency, or non-PostgreSQL feature enters these milestones.

---

## M1 — Specification and repository foundation

**Duration:** 3–4 weeks  
**Estimated effort:** 30–40 hours  
**Release target:** internal `0.0.x`; no public product claim  

### Milestone goal

Freeze the Boundary Contract and produce a reproducible repository in which the core API, PostgreSQL environment, packaging, and CI can be exercised before security-critical implementation begins.

### Milestone exit gate

- [ ] No unresolved ambiguity remains in event/delivery identity, route snapshots, dedupe, replay, RLS trust, authorization modes, or lease behavior.
- [ ] A clean wheel installs and imports both with base dependencies and with the `webhooks` extra.
- [ ] The architecture review checklist passes and every M2/M3 task maps to the frozen MDP.
- [ ] The invoicing example boots against the integration PostgreSQL service, even though core operations are still stubs.

### Work items

### - [ ] M1.01 — Create the repository and `src`-layout package scaffold

**Estimate:** 3 h  
**Depends on:** None

**Goal**

Create the canonical repository tree, a collision-free import package, and the minimum files required for local development and packaging.

**Context**

The packaging strategy is intentionally one distribution (`fastapi-mergen`) with one import root (`fastapi_mergen`). Starting with the final namespace and `src` layout prevents accidental imports from the working tree and avoids a later namespace migration.

**Affected files**

- `pyproject.toml`
- `src/fastapi_mergen/__init__.py`
- `src/fastapi_mergen/api.py`
- `src/fastapi_mergen/errors.py`
- `src/fastapi_mergen/py.typed`
- `tests/__init__.py`
- `.gitignore`
- `LICENSE`

**Definition of Done**

- [ ] `python -c "import fastapi_mergen"` succeeds only after editable or wheel installation, not merely because the repository root is on `sys.path`.
- [ ] The built wheel contains `fastapi_mergen/py.typed` and no accidental top-level `mergen` package.
- [ ] `fastapi_mergen.__all__` contains only the intentionally public placeholder symbols.
- [ ] Repository paths match the audited plan and contain no premature queue, MCP, workflow, or idempotency package.

### - [ ] M1.02 — Define package metadata, extras, and version ownership

**Estimate:** 3 h  
**Depends on:** M1.01

**Goal**

Make distribution metadata, dependency groups, console entry point, and version retrieval deterministic before implementation begins.

**Context**

The base package must import without webhook or observability dependencies. Optional features belong behind extras, and the console script must use `fastapi-mergen` rather than the occupied generic `mergen` name.

**Affected files**

- `pyproject.toml`
- `src/fastapi_mergen/_version.py` or selected SCM-version configuration
- `src/fastapi_mergen/cli/__init__.py`
- `src/fastapi_mergen/cli/main.py`
- `tests/packaging/test_metadata.py`

**Definition of Done**

- [ ] Project name is `fastapi-mergen`; import root is `fastapi_mergen`; console entry point is `fastapi-mergen`.
- [ ] Base, `webhooks`, `otel`, development, documentation, and test dependencies are separated without circular extras.
- [ ] Version is exposed as `fastapi_mergen.__version__` from one authoritative source.
- [ ] Metadata includes supported Python versions, licence, typed-package classifier/marker, project URLs, and an explicit pre-alpha status.

### - [ ] M1.03 — Establish linting, formatting, typing, and test conventions

**Estimate:** 3 h  
**Depends on:** M1.01–M1.02

**Goal**

Create one deterministic local quality command and strict enough static checks for a security-sensitive asynchronous library.

**Context**

Repository governance must be fixed before code volume grows. The checks should catch accidental public API expansion, untyped async boundaries, unsafe broad exceptions, and test isolation problems without requiring manually different commands in CI and locally.

**Affected files**

- `pyproject.toml`
- `uv.lock`
- `scripts/check.sh` or `scripts/check.py`
- `tests/conftest.py`
- `CONTRIBUTING.md`

**Definition of Done**

- [ ] Ruff formatting/linting, mypy or pyright strict project configuration, and pytest configuration are committed.
- [ ] One documented command runs formatting check, lint, type check, unit tests, and package build.
- [ ] Async tests use one documented event-loop policy and do not share mutable global state.
- [ ] Warnings are treated as errors in library tests except for explicitly documented third-party exceptions.

### - [ ] M1.04 — Build the CI and clean-artifact packaging matrix

**Estimate:** 4 h  
**Depends on:** M1.01–M1.03

**Goal**

Prove that source, wheel, extras, minimum dependencies, and supported Python versions behave consistently in clean environments.

**Context**

A package can pass tests from a checkout while shipping a broken wheel or undeclared dependency. Packaging correctness is therefore a milestone gate, not release cleanup.

**Affected files**

- `.github/workflows/ci.yml`
- `.github/workflows/package.yml`
- `.github/workflows/security.yml`
- `tests/packaging/test_clean_install.py`
- `tests/packaging/test_optional_imports.py`
- `scripts/build_and_test_artifacts.py`

**Definition of Done**

- [ ] CI runs lint/type/unit checks on the supported Python matrix and a bounded pairwise integration matrix.
- [ ] Separate jobs install the wheel with base dependencies, `webhooks`, and `otel` extras.
- [ ] Base import succeeds without HTTPX, cryptography, Standard Webhooks, or OpenTelemetry installed; feature imports fail with actionable optional-dependency errors.
- [ ] Both sdist and wheel are built and smoke-tested in clean virtual environments.
- [ ] No publish job can run from an untrusted pull request; future publishing is prepared for OIDC/trusted publishing.

### - [ ] M1.05 — Freeze Boundary Contract v0.1 and guarantee vocabulary

**Estimate:** 3 h  
**Depends on:** None

**Goal**

Turn the product thesis into normative, testable guarantees and explicit non-guarantees.

**Context**

Terms such as atomic, at-least-once, effectively once, retry, replay, ordering, and cancellation must have one meaning across code, docs, tests, and marketing. This prevents the exactly-once overclaim from returning through examples or API naming.

**Affected files**

- `docs/concepts/boundary-contract.md`
- `docs/concepts/guarantees.md`
- `docs/index.md`
- `README.md`
- `docs/reference/glossary.md`

**Definition of Done**

- [ ] The seven invariants are stated normatively with SHALL/MUST/DOES NOT language where appropriate.
- [ ] The guarantee table distinguishes local atomicity, at-least-once delivery, stable retry identity, effectively-once consumer behavior, and replay.
- [ ] Ordering and cancellation are explicitly unsupported in the MDP.
- [ ] Every guarantee has a named future conformance test or a reason it is documentation-only.
- [ ] README terminology matches the contract and contains no generic exactly-once claim.

### - [ ] M1.06 — Write the threat model and trust-boundary specification

**Estimate:** 3 h  
**Depends on:** M1.05

**Goal**

Define trusted actors, hostile inputs, protected assets, failure modes, and security limitations before choosing implementation shortcuts.

**Context**

RLS protects against classes of application mistakes, not full compromise of an application credential. Likewise, the relay is cross-tenant on Mergen tables but must not become a business-data superuser. These limits must be visible and testable.

**Affected files**

- `docs/concepts/threat-model.md`
- `docs/concepts/authorization.md`
- `SECURITY.md`
- `docs/operations/roles-and-rls.md`
- `docs/adr/0001-trust-model.md`

**Definition of Done**

- [ ] Assets, trust zones, attacker capabilities, and non-goals are listed.
- [ ] Threats include cross-tenant access, pool leakage, stale workers, authorization revocation, SSRF, secret/log leakage, unsafe grants, and replay misuse.
- [ ] The limitation of application-set PostgreSQL tenant context is stated without presenting it as database-native authentication.
- [ ] Each high-severity threat maps to a mitigation, a diagnostic, a conformance test, or an explicitly accepted residual risk.

### - [ ] M1.07 — Approve the explicit unit-of-work transaction ADR

**Estimate:** 2 h  
**Depends on:** M1.05–M1.06

**Goal**

Freeze transaction ownership, tenant binding, nesting, savepoint, commit/rollback, and cleanup semantics.

**Context**

The security-critical first implementation must not depend on hidden global SQLAlchemy listeners. Requiring an outermost Mergen UoW narrows the integration surface and gives `emit()` a provable transaction boundary.

**Affected files**

- `docs/adr/0002-explicit-uow-transaction.md`
- `docs/concepts/boundary-contract.md`
- `docs/reference/uow-lifecycle.md`

**Definition of Done**

- [ ] ADR states that UoW entry fails when the supplied session already has a transaction.
- [ ] Tenant `SET LOCAL` occurs before application SQL and cleanup occurs in `finally`.
- [ ] Nested Mergen UoWs are rejected; application savepoints after binding are permitted and documented.
- [ ] The ADR includes sequence diagrams for success, application exception, commit failure, cancellation, and dependency-finalizer failure.

### - [ ] M1.08 — Approve event/delivery/attempt identity, dedupe, and replay ADR

**Estimate:** 3 h  
**Depends on:** M1.05–M1.06

**Goal**

Freeze row identity, tenant-safe references, dedupe conflict behavior, automatic retry identity, and manual replay lineage.

**Context**

A single outbox row cannot represent independent destinations. The schema needs immutable events, one delivery per destination, append-only attempts, and replay as a new delivery rather than mutation of terminal history.

**Affected files**

- `docs/adr/0003-event-delivery-attempt-model.md`
- `docs/concepts/guarantees.md`
- `docs/reference/data-model.md`

**Definition of Done**

- [ ] ADR fixes event, delivery, and attempt responsibilities and composite tenant-safe foreign keys.
- [ ] Dedupe key namespace, unique constraint, canonical payload hash, compatible-hit behavior, and mismatch error are specified.
- [ ] Automatic retry keeps delivery identity; manual replay creates a new linked delivery/message identity.
- [ ] The ADR defines which terminal fields may never be changed and how retention may delete historical rows.

### - [ ] M1.09 — Approve route, destination, and authorization snapshot ADR

**Estimate:** 2 h  
**Depends on:** M1.05–M1.08

**Goal**

Freeze exact route matching and the immutable data captured for each destination at emission time.

**Context**

Retries must not be reinterpreted through later code/configuration changes. Authorization also needs explicit provenance: attenuated snapshot, current revalidation, or a separately named service policy.

**Affected files**

- `docs/adr/0004-routing-and-policy-snapshots.md`
- `docs/concepts/authorization.md`
- `docs/reference/route-snapshot-schema.md`

**Definition of Done**

- [ ] Exact event-type matching and startup registry freeze are normative.
- [ ] Route key/version, destination snapshot schema, policy snapshot schema, and retry profile version are fixed.
- [ ] `snapshot` and `revalidate` non-expansion formulae are documented.
- [ ] `service_policy` is explicitly represented as service authority rather than silently expanded user authority.
- [ ] No plaintext secret, raw credential, or Python callable is allowed in a snapshot.

### - [ ] M1.10 — Approve relay lease, fairness, retry, and shutdown ADR

**Estimate:** 3 h  
**Depends on:** M1.08–M1.09

**Goal**

Freeze the delivery state machine and all crash-sensitive transitions before SQL is written.

**Context**

The relay must claim quickly, perform work outside locks, reject stale finalization, count attempts at claim, and avoid a single tenant monopolizing batches. Polling remains authoritative.

**Affected files**

- `docs/adr/0005-relay-state-machine.md`
- `docs/operations/relay.md`
- `docs/operations/retries-and-replay.md`
- `docs/reference/failure-taxonomy.md`

**Definition of Done**

- [ ] State diagram and legal transitions cover pending, leased, retry-wait, succeeded, and dead.
- [ ] Claim, renewal, finalization, lease-loss, and abandoned-attempt transactions are specified with compare-and-set predicates.
- [ ] Attempt count timing, full-jitter retry, deadlines, and `Retry-After` clamping are unambiguous.
- [ ] Fairness promises bounded unfairness, not strict ordering.
- [ ] Graceful shutdown and kill-point matrix are enumerated.

### - [ ] M1.11 — Implement and evaluate the narrow public API spike

**Estimate:** 4 h  
**Depends on:** M1.07–M1.10

**Goal**

Exercise the proposed API in type-checked example code before committing to internals.

**Context**

The spike should reveal whether `Mergen`, route declarations, `MergenUnitOfWork`, `Event`, `EffectContext`, authorization modes, and retry profiles compose naturally without exposing repository or SQL details.

**Affected files**

- `src/fastapi_mergen/api.py`
- `src/fastapi_mergen/core/protocols.py`
- `examples/invoicing/app/api.py`
- `examples/invoicing/app/mergen_config.py`
- `tests/unit/test_public_api_spike.py`
- `docs/reference/public-api-spike.md`

**Definition of Done**

- [ ] Example route registration, request UoW, emission, and handler definitions type-check.
- [ ] The root package exposes no repository, SQL expression, DBAPI, or HTTP client internals.
- [ ] A user can replace principal, authorization, clock, random, and handler-session providers through explicit protocols.
- [ ] The spike records rejected alternatives and resulting API changes in the ADR log.

### - [ ] M1.12 — Create the PostgreSQL integration-test environment

**Estimate:** 3 h  
**Depends on:** M1.01–M1.04

**Goal**

Provide a deterministic disposable PostgreSQL environment for migrations, roles, RLS, pooling, concurrency, and crash tests.

**Context**

SQLite or mocks cannot validate the required behavior. The test environment must be able to connect as migration owner, app role, relay role, and an intentionally misconfigured role.

**Affected files**

- `compose.yaml`
- `tests/integration/conftest.py`
- `tests/integration/postgres.py`
- `scripts/wait_for_postgres.py`
- `.env.example`
- `.github/workflows/ci.yml`

**Definition of Done**

- [ ] A single documented command starts PostgreSQL and provisions isolated test databases.
- [ ] Fixtures expose migration-owner, app, relay, and misconfiguration connection URLs without embedding production-like secrets.
- [ ] Tests can reset schema state without race-prone shared databases.
- [ ] CI runs the environment against the selected oldest and newest certified PostgreSQL versions.

### - [ ] M1.13 — Create the invoicing skeleton and run the Milestone 1 architecture gate

**Estimate:** 4 h  
**Depends on:** M1.01–M1.12

**Goal**

Validate the full planned repository shape and freeze the implementation backlog before Milestone 2.

**Context**

The example is the contract consumer. It should demonstrate tenant-authenticated request wiring, an application model, effect DTO, route declaration, handler shape, and future webhook configuration while core methods remain explicit stubs.

**Affected files**

- `examples/invoicing/app/main.py`
- `examples/invoicing/app/models.py`
- `examples/invoicing/app/schemas.py`
- `examples/invoicing/app/auth.py`
- `examples/invoicing/app/mergen_config.py`
- `examples/invoicing/tests/test_boot.py`
- `docs/adr/README.md`
- `docs/milestone-1-review.md`

**Definition of Done**

- [ ] Reference application boots and its OpenAPI schema renders against the integration environment.
- [ ] The example imports only planned public APIs and contains no hidden shortcut around the UoW.
- [ ] Architecture checklist confirms all frozen decisions and records every remaining question with owner and blocking status.
- [ ] M2/M3 task estimates total within the roadmap envelope or the roadmap is revised before implementation.
- [ ] Milestone 1 exit gate is signed off in `docs/milestone-1-review.md`.

---

## M2 — Core transactional effect engine

**Duration:** 10–12 weeks  
**Estimated effort:** 100–130 hours  
**Release target:** limited `v0.1.0a1`  

### Milestone goal

Implement the principal-aware PostgreSQL event ledger, explicit UoW, RLS/role model, lease relay, in-process handler sink, diagnostics, and core conformance/chaos suites.

### Milestone exit gate

- [ ] Core suites pass on PostgreSQL 16 and 18 with the reference async driver.
- [ ] Kill-at-each-boundary testing demonstrates no lost committed delivery and only documented duplicates.
- [ ] A stale worker cannot renew or finalize work after lease replacement.
- [ ] Sequential and concurrent two-tenant executions leak no principal, dependency, or session state.
- [ ] The relay role has no access to application business tables.
- [ ] At least one external design partner accepts the API and schema for serious evaluation.

### Work items

### - [ ] M2.01 — Implement public protocols, result types, and exception taxonomy

**Estimate:** 3 h  
**Depends on:** M1 complete

**Goal**

Create stable typed contracts used by core, PostgreSQL, handlers, diagnostics, and tests without exposing implementation classes.

**Context**

A narrow public surface lets storage and execution internals change while preserving user code. Exceptions must distinguish configuration, authorization, dedupe, retryable delivery, permanent delivery, lease loss, and schema mismatch.

**Affected files**

- `src/fastapi_mergen/core/protocols.py`
- `src/fastapi_mergen/errors.py`
- `src/fastapi_mergen/api.py`
- `src/fastapi_mergen/__init__.py`
- `tests/unit/test_public_contracts.py`

**Definition of Done**

- [ ] Protocols cover principal provider, authorization resolver, handler session factory, clock, random source, event store, and sink executor.
- [ ] Public exceptions have stable attributes, safe string representations, and no secret/payload inclusion.
- [ ] Root exports match the documented API exactly.
- [ ] Type-checking tests demonstrate third-party protocol implementations without subclassing internals.

### - [ ] M2.02 — Implement the immutable `Principal` model

**Estimate:** 4 h  
**Depends on:** M2.01

**Goal**

Represent authenticated tenant and authority provenance in a validated, immutable, serializable form.

**Context**

Principal data will be snapshotted into events and restored during delayed execution. It must distinguish subject, optional actor/client, origin scopes, timestamps, and opaque references without storing raw credentials.

**Affected files**

- `src/fastapi_mergen/core/principal.py`
- `src/fastapi_mergen/core/policy.py`
- `tests/unit/core/test_principal.py`
- `docs/reference/principal.md`

**Definition of Done**

- [ ] Tenant ID and subject ID are required and normalized; model is immutable/hash-safe where appropriate.
- [ ] Scope names are syntactically validated, deduplicated, deterministically ordered, and bounded.
- [ ] Timestamp ordering and optional expiry constraints are validated.
- [ ] Serialization excludes all raw credential classes and rejects unknown secret-like fields in principal metadata.
- [ ] Property tests cover malformed identifiers, excessive scopes, duplicate scopes, and round trips.

### - [ ] M2.03 — Implement principal `ContextVar` lifecycle and leak guards

**Estimate:** 3 h  
**Depends on:** M2.02

**Goal**

Provide ergonomic current-principal access while guaranteeing reset across success, failure, cancellation, and concurrent tasks.

**Context**

The context variable is process-local convenience, not durable authority. It must always be populated from a trusted principal and reset through its token; no worker attempt may inherit a previous attempt’s context.

**Affected files**

- `src/fastapi_mergen/core/context.py`
- `src/fastapi_mergen/testing/context.py`
- `tests/unit/core/test_context.py`
- `tests/conformance/test_context_lifecycle.py`

**Definition of Done**

- [ ] Context manager sets and resets using the exact `ContextVar` token.
- [ ] Access outside a bound context raises a documented exception rather than returning stale/default principal.
- [ ] Concurrent task tests prove isolation among tenants.
- [ ] Success, exception, cancellation, and nested-attempt rejection tests leave no bound principal.

### - [ ] M2.04 — Implement typed events, canonical JSON, and payload hashing

**Estimate:** 4 h  
**Depends on:** M2.01–M2.02

**Goal**

Produce deterministic event data and hashes suitable for dedupe conflict detection and stable wire snapshots.

**Context**

Arbitrary ORM serialization is forbidden. Event DTOs need positive schema versions, bounded canonical payloads, deterministic hash bytes, and explicit correlation/causation/trace fields.

**Affected files**

- `src/fastapi_mergen/core/event.py`
- `src/fastapi_mergen/sqlalchemy/canonical.py`
- `tests/unit/core/test_event.py`
- `tests/unit/sqlalchemy/test_canonical.py`
- `tests/fixtures/canonical_vectors.json`

**Definition of Done**

- [ ] Only supported typed DTO/model inputs are accepted; ORM instances and unserializable objects fail clearly.
- [ ] Canonical bytes are stable across dictionary order and supported runtime versions.
- [ ] Payload byte-size limit is enforced before database insertion.
- [ ] SHA-256 hash is computed over the canonical representation and verified against committed test vectors.
- [ ] Correlation, causation, trace, occurred-at, type, and schema version validation is complete.

### - [ ] M2.05 — Implement retry and authorization policy value objects

**Estimate:** 3 h  
**Depends on:** M2.01–M2.04

**Goal**

Represent immutable, versioned policy snapshots with validation independent of the relay implementation.

**Context**

A delivery cannot depend on a mutable named profile alone. The route snapshot stores resolved values so retries remain stable after configuration changes.

**Affected files**

- `src/fastapi_mergen/core/retry.py`
- `src/fastapi_mergen/core/policy.py`
- `tests/unit/core/test_retry_policy.py`
- `tests/unit/core/test_authorization_policy.py`

**Definition of Done**

- [ ] Retry policy validates attempts, elapsed time, delays, timeout, lease duration, and full-jitter mode.
- [ ] Authorization mode is limited to snapshot, revalidate, and service policy with mode-specific required fields.
- [ ] Snapshot maximum age and origin scope ceiling are represented explicitly.
- [ ] Policy serialization is deterministic, versioned, and safe for JSONB storage.

### - [ ] M2.06 — Implement exact route registry and startup freeze

**Estimate:** 4 h  
**Depends on:** M2.01–M2.05

**Goal**

Create deterministic route registration, validation, lookup, and immutable delivery specifications.

**Context**

Routes must never be resolved from mutable function names at retry time. The registry freezes at startup and resolves exact event types into versioned route specifications.

**Affected files**

- `src/fastapi_mergen/core/routing.py`
- `src/fastapi_mergen/handlers/registry.py`
- `src/fastapi_mergen/api.py`
- `tests/unit/core/test_routing.py`
- `tests/integration/test_startup_registry.py`

**Definition of Done**

- [ ] Duplicate route key/version, missing handler, invalid retry policy, and unresolved service policy fail startup.
- [ ] Registration after freeze raises a configuration error.
- [ ] Lookup is exact by event type and returns deterministic route order.
- [ ] Route specifications contain only serializable snapshot data and stable handler/destination keys.
- [ ] Unsupported route version downgrade is detected against configured compatibility metadata.

### - [ ] M2.07 — Implement SQLAlchemy models and database invariants

**Estimate:** 5 h  
**Depends on:** M2.02–M2.06

**Goal**

Encode the audited event, delivery, and attempt schema in SQLAlchemy without weakening database constraints.

**Context**

ORM models are a mapping layer, not the source of truth for invariants. Composite tenant-safe references, partial indexes, status checks, replay lineage, and immutable fields must match the SQL design.

**Affected files**

- `src/fastapi_mergen/sqlalchemy/models.py`
- `src/fastapi_mergen/sqlalchemy/types.py`
- `tests/unit/sqlalchemy/test_models.py`
- `tests/integration/test_database_constraints.py`

**Definition of Done**

- [ ] Event, delivery, and attempt mappings exactly match required columns and nullability.
- [ ] Composite foreign keys prevent cross-tenant event/delivery/attempt/replay references.
- [ ] Partial unique/index definitions compile correctly for PostgreSQL.
- [ ] Status/lease/terminal check constraints reject impossible states through direct SQL tests.
- [ ] ORM relationships do not introduce implicit lazy loads in relay-critical paths.

### - [ ] M2.08 — Create reversible core-schema Alembic migrations

**Estimate:** 5 h  
**Depends on:** M2.07

**Goal**

Install and remove the Mergen schema, tables, indexes, functions, and schema revision metadata deterministically.

**Context**

The package must never auto-migrate at runtime. Migrations need a stable naming convention, explicit PostgreSQL SQL where Alembic abstractions are insufficient, and clean upgrade/downgrade tests.

**Affected files**

- `src/fastapi_mergen/postgres/migrations/env.py`
- `src/fastapi_mergen/postgres/migrations/script.py.mako`
- `src/fastapi_mergen/postgres/migrations/versions/0001_core_schema.py`
- `src/fastapi_mergen/postgres/migrations/versions/0002_schema_metadata.py`
- `tests/integration/test_migrations.py`

**Definition of Done**

- [ ] Upgrade creates the dedicated schema, all core tables, constraints, indexes, and revision metadata.
- [ ] Downgrade succeeds on a clean database and documents destructive limitations.
- [ ] Upgrade → downgrade → upgrade produces an equivalent inspected schema.
- [ ] Migration SQL is schema-qualified and does not rely on a mutable search path.
- [ ] Migration package data is present in sdist and wheel.

### - [ ] M2.09 — Implement migration-owner, app-role, and relay-role grants

**Estimate:** 4 h  
**Depends on:** M2.08

**Goal**

Provision the fixed least-privilege database role model and make unsafe ownership/grants detectable.

**Context**

The relay needs cross-tenant access to Mergen control-plane rows but must not read application business tables. Runtime roles must not own tables or bypass RLS.

**Affected files**

- `src/fastapi_mergen/postgres/roles.py`
- `src/fastapi_mergen/postgres/migrations/versions/0003_roles_and_grants.py`
- `tests/security/test_role_grants.py`
- `docs/operations/roles-and-rls.md`

**Definition of Done**

- [ ] Migration-owner, app, and relay roles can be parameterized without interpolating unsafe identifiers.
- [ ] Runtime roles are granted only required schema/table/sequence/function privileges.
- [ ] Relay role has no grants on configured application schemas and no delete privilege on Mergen history.
- [ ] Ownership remains with the migration role; runtime-role ownership tests fail intentionally misconfigured databases.
- [ ] Role creation can be disabled for managed platforms while emitting exact required SQL/grant documentation.

### - [ ] M2.10 — Implement fail-closed RLS functions and policies

**Estimate:** 5 h  
**Depends on:** M2.08–M2.09

**Goal**

Enforce tenant isolation on every Mergen tenant table for request/handler sessions while preserving narrowly scoped relay access.

**Context**

Policies require both `USING` and `WITH CHECK`, forced RLS, non-owner runtime roles, and live tests for missing tenant settings and cross-tenant writes.

**Affected files**

- `src/fastapi_mergen/postgres/rls.py`
- `src/fastapi_mergen/postgres/migrations/versions/0004_rls.py`
- `tests/security/test_rls_read_write.py`
- `tests/security/test_rls_misconfiguration.py`

**Definition of Done**

- [ ] Current-tenant helper returns null/fails closed when no valid transaction-local tenant is bound.
- [ ] Every tenant table has RLS enabled and forced.
- [ ] App policies apply both `USING` and `WITH CHECK`; direct cross-tenant select/insert/update/delete probes fail.
- [ ] Relay policies apply only to Mergen-owned tables and permit exactly the operations needed by the relay.
- [ ] Table-owner, superuser, and `BYPASSRLS` configurations are covered by explicit negative diagnostic tests.

### - [ ] M2.11 — Implement the explicit SQLAlchemy `MergenUnitOfWork`

**Estimate:** 6 h  
**Depends on:** M2.02–M2.10

**Goal**

Own the outer transaction, bind tenant context before SQL, expose an active emission boundary, and guarantee cleanup.

**Context**

The UoW is the core correctness boundary. It must reject ambiguous pre-existing transactions and nested Mergen UoWs rather than attempting to infer transaction ownership.

**Affected files**

- `src/fastapi_mergen/sqlalchemy/uow.py`
- `src/fastapi_mergen/sqlalchemy/session_state.py`
- `tests/unit/sqlalchemy/test_uow.py`
- `tests/integration/test_uow_transactions.py`
- `tests/conformance/test_atomicity.py`

**Definition of Done**

- [ ] Entry rejects an already active transaction and a nested Mergen UoW with actionable errors.
- [ ] Transaction begins explicitly and `set_config(..., true)` executes before application statements.
- [ ] Success commits once; application exception, cancellation, emit failure, and commit failure roll back correctly.
- [ ] Principal context and session metadata reset in `finally`, including failed cleanup paths.
- [ ] `emit()` outside the active UoW and after exit raises a deterministic error.

### - [ ] M2.12 — Integrate trusted principal resolution with FastAPI UoW dependencies

**Estimate:** 4 h  
**Depends on:** M2.02–M2.03, M2.11

**Goal**

Provide a supported request integration that resolves the principal before the UoW and does not trust raw tenant headers by default.

**Context**

Mergen is auth-agnostic. The application adapter is responsible for authentication and tenant membership, while Mergen validates the returned principal and lifecycle.

**Affected files**

- `src/fastapi_mergen/api.py`
- `src/fastapi_mergen/integrations/fastapi.py`
- `tests/integration/test_fastapi_dependency.py`
- `tests/security/test_conflicting_tenant_sources.py`
- `examples/invoicing/app/auth.py`

**Definition of Done**

- [ ] Principal provider protocol supports async implementations and produces one validated principal per request.
- [ ] UoW dependency obtains a fresh session without performing application SQL before tenant binding.
- [ ] Provider failure, tenant disagreement, missing membership, and malformed principal fail before UoW entry.
- [ ] Request completion and dependency errors leave no principal or open session.
- [ ] Documentation states that raw tenant headers are candidates only, never authorization proof.

### - [ ] M2.13 — Implement atomic event emission and original-delivery snapshot insertion

**Estimate:** 6 h  
**Depends on:** M2.04–M2.12

**Goal**

Persist the event and every original delivery through the active application transaction with no partial fan-out.

**Context**

Emission validates the event, resolves routes, creates immutable snapshots, and inserts all rows before the application transaction commits. A sink is never invoked during emission.

**Affected files**

- `src/fastapi_mergen/sqlalchemy/uow.py`
- `src/fastapi_mergen/sqlalchemy/repository.py`
- `src/fastapi_mergen/core/delivery.py`
- `tests/integration/test_emit_atomic.py`
- `tests/conformance/test_atomicity.py`

**Definition of Done**

- [ ] Event and all original deliveries are inserted in the caller’s active UoW transaction.
- [ ] Zero matching routes has a documented configurable behavior and does not accidentally create orphan state.
- [ ] Any snapshot/insert failure rolls back application rows, event, and all deliveries.
- [ ] No handler, webhook, queue, or notification side effect occurs before commit.
- [ ] Returned emission result exposes stable event and delivery IDs without ORM session leakage.

### - [ ] M2.14 — Implement race-safe event dedupe and conflict detection

**Estimate:** 4 h  
**Depends on:** M2.04, M2.08, M2.13

**Goal**

Make concurrent duplicate emissions converge to one event and one original route snapshot set without hiding payload conflicts.

**Context**

Dedupe uses tenant, namespace, and key. A later compatible call must return the first event and must not route against a newer registry; a payload mismatch must fail explicitly.

**Affected files**

- `src/fastapi_mergen/sqlalchemy/repository.py`
- `src/fastapi_mergen/sqlalchemy/canonical.py`
- `tests/integration/test_dedupe.py`
- `tests/chaos/test_dedupe_race.py`

**Definition of Done**

- [ ] Concurrent compatible inserts yield one event and one set of original deliveries.
- [ ] Compatible dedupe hit compares tenant, event type, schema version, and payload hash.
- [ ] Mismatched payload/type/version raises `DedupeConflict` with no payload content in the error.
- [ ] A dedupe hit does not insert routes added after the original event.
- [ ] Tests exercise at least 20 concurrent contenders and transaction rollback of the winner.

### - [ ] M2.15 — Implement repository read/query contracts

**Estimate:** 3 h  
**Depends on:** M2.07–M2.14

**Goal**

Centralize schema-qualified persistence operations and prevent arbitrary ORM query construction in relay-critical code.

**Context**

Repository methods should expose domain results and explicit transaction expectations. Request-role and relay-role methods differ and should not be accidentally interchangeable.

**Affected files**

- `src/fastapi_mergen/sqlalchemy/repository.py`
- `src/fastapi_mergen/core/protocols.py`
- `tests/unit/sqlalchemy/test_repository_contract.py`
- `tests/integration/test_repository_roles.py`

**Definition of Done**

- [ ] Methods declare whether they require app or relay role and active transaction.
- [ ] All SQL is schema-qualified and parameterized.
- [ ] Domain objects are detached/immutable enough to survive session closure.
- [ ] Attempt history and replay lineage queries are tenant-safe and bounded/paginated.

### - [ ] M2.16 — Implement atomic claim SQL and attempt-start accounting

**Estimate:** 6 h  
**Depends on:** M2.08–M2.10, M2.15

**Goal**

Claim due deliveries with short transactions, fresh lease tokens, and an append-only attempt row inserted atomically.

**Context**

Locks must not be held during handler work. Claiming increments attempts started, establishes the token used by every later update, and uses database time at READ COMMITTED isolation.

**Affected files**

- `src/fastapi_mergen/postgres/leasing.py`
- `src/fastapi_mergen/sqlalchemy/repository.py`
- `tests/integration/test_claiming.py`
- `tests/chaos/test_concurrent_claimers.py`

**Definition of Done**

- [ ] Claim uses `FOR UPDATE SKIP LOCKED`, sets lease fields, increments attempt count, and inserts attempt in one transaction.
- [ ] Network/handler execution cannot occur inside the claim transaction API.
- [ ] Concurrent workers never claim the same delivery with the same current lease.
- [ ] Database timestamps drive due and lease calculations.
- [ ] Claim results contain immutable event/delivery snapshots and no live ORM session.

### - [ ] M2.17 — Implement bounded per-tenant fairness selection

**Estimate:** 3 h  
**Depends on:** M2.16

**Goal**

Prevent one high-volume tenant from filling every worker batch without claiming strict global ordering.

**Context**

The worker first selects a bounded tenant set by oldest due work, rotates the start point, and claims no more than the per-tenant limit before filling the batch.

**Affected files**

- `src/fastapi_mergen/postgres/leasing.py`
- `src/fastapi_mergen/postgres/relay.py`
- `tests/integration/test_tenant_fairness.py`

**Definition of Done**

- [ ] Configuration validates batch size, tenant scan limit, and per-tenant claim limit.
- [ ] A noisy tenant cannot starve a continuously due low-volume tenant in the documented bounded scenario.
- [ ] Multiple workers remain safe under `SKIP LOCKED` and may be unfair only within the stated bound.
- [ ] Documentation explicitly avoids an ordering/SLA guarantee.

### - [ ] M2.18 — Implement lease-token compare-and-set finalization

**Estimate:** 4 h  
**Depends on:** M2.16

**Goal**

Finalize success or failure only for the currently held lease and update attempt/delivery state consistently.

**Context**

A stale process may finish after another worker has reclaimed the delivery. Every finalization must predicate on delivery ID, leased status, and exact lease token.

**Affected files**

- `src/fastapi_mergen/postgres/leasing.py`
- `src/fastapi_mergen/sqlalchemy/repository.py`
- `tests/integration/test_finalize.py`
- `tests/chaos/test_stale_finalize.py`

**Definition of Done**

- [ ] Success, retryable failure, and terminal failure transitions update attempt and delivery in one transaction.
- [ ] Lease fields clear only on a matching current token.
- [ ] Mismatched/stale token changes no delivery state and produces a `LeaseLost` result/metric.
- [ ] Terminal states set `terminal_at` and cannot be finalized a second time.
- [ ] One delivery finalization never modifies sibling destination rows.

### - [ ] M2.19 — Implement lease renewal and abandoned-attempt reconciliation

**Estimate:** 4 h  
**Depends on:** M2.16–M2.18

**Goal**

Support long-running handlers without permitting stale heartbeats or leaving unfinished attempts permanently ambiguous.

**Context**

Renewal is a token-checked compare-and-set operation. Expired deliveries can be reclaimed directly; the prior unfinished attempt must eventually be marked abandoned without overwriting a newer attempt.

**Affected files**

- `src/fastapi_mergen/postgres/leasing.py`
- `src/fastapi_mergen/postgres/relay.py`
- `tests/integration/test_lease_renewal.py`
- `tests/chaos/test_expired_lease_reclaim.py`

**Definition of Done**

- [ ] Renewal requires matching ID, leased status, token, and non-expired/currently valid policy.
- [ ] A stale worker cannot extend a replacement worker’s lease.
- [ ] Reclaim creates a new attempt number/token and leaves history append-only.
- [ ] Prior incomplete attempt becomes `abandoned` exactly once through bounded reconciliation.
- [ ] Metrics distinguish renewal failure, expired lease, abandonment, and stale completion.

### - [ ] M2.20 — Implement retry scheduling, deadlines, and failure classification

**Estimate:** 4 h  
**Depends on:** M2.05, M2.18

**Goal**

Convert execution outcomes into deterministic retry-wait or dead state using immutable policy snapshots.

**Context**

Retry timing uses full jitter with injected test randomness, but persisted dates use database time. Max attempts and delivery deadline are hard bounds.

**Affected files**

- `src/fastapi_mergen/core/retry.py`
- `src/fastapi_mergen/postgres/leasing.py`
- `tests/unit/core/test_backoff.py`
- `tests/integration/test_retry_deadline.py`

**Definition of Done**

- [ ] Full-jitter delay remains within validated base/exponential/max bounds.
- [ ] No attempt is scheduled after maximum elapsed time or delivery deadline.
- [ ] Permanent failures go dead immediately; unknown handler errors follow documented retry behavior.
- [ ] Injected clock/random yield deterministic unit tests; database scheduling remains authoritative.
- [ ] Error summaries are bounded and sanitized before persistence.

### - [ ] M2.21 — Implement the polling relay supervisor and graceful shutdown

**Estimate:** 5 h  
**Depends on:** M2.16–M2.20

**Goal**

Run multiple bounded worker loops safely with polling, concurrency limits, backpressure, and deterministic shutdown behavior.

**Context**

The supervisor coordinates tenant selection, claims, sink execution, lease heartbeat, reconciliation, and finalization. It must stop claiming before draining active work.

**Affected files**

- `src/fastapi_mergen/postgres/relay.py`
- `src/fastapi_mergen/cli/relay.py`
- `src/fastapi_mergen/observability/relay.py`
- `tests/integration/test_relay_loop.py`
- `tests/chaos/test_relay_shutdown.py`

**Definition of Done**

- [ ] Global worker, per-tenant, and per-destination concurrency bounds are enforced.
- [ ] Idle polling uses bounded backoff and does not busy-loop.
- [ ] Shutdown stops new claims, drains/cancels according to grace policy, closes sessions, and resets contexts.
- [ ] Unexpected supervisor task failure causes a non-zero process exit rather than silent partial operation.
- [ ] No `LISTEN/NOTIFY` dependency is introduced in the correctness path.

### - [ ] M2.22 — Implement the in-process handler sink with separate application sessions

**Estimate:** 5 h  
**Depends on:** M2.03, M2.06, M2.11, M2.21

**Goal**

Execute registered async handlers with an `EffectContext`, fresh tenant-bound app session, and per-attempt dependency lifecycle.

**Context**

The relay control-plane session must never be injected into handler code. Handler dependencies are application-provided and must be scoped and finalized for each attempt.

**Affected files**

- `src/fastapi_mergen/handlers/registry.py`
- `src/fastapi_mergen/handlers/executor.py`
- `src/fastapi_mergen/handlers/dependencies.py`
- `tests/integration/test_handler_execution.py`
- `tests/conformance/test_handler_lifecycle.py`

**Definition of Done**

- [ ] Handler lookup uses snapshotted route key/version and fails terminally when unsupported.
- [ ] Execution binds principal context and opens a fresh `mergen_app` transaction before application SQL.
- [ ] Relay session/connection is not exposed through `EffectContext` or dependency providers.
- [ ] Yielded dependencies finalize on success, exception, timeout, and cancellation.
- [ ] Sequential/concurrent tenant tests show distinct sessions and no dependency cache leakage.

### - [ ] M2.23 — Implement snapshot, revalidate, and service-policy authorization

**Estimate:** 5 h  
**Depends on:** M2.02, M2.05, M2.13, M2.22

**Goal**

Resolve an explicit execution authority for every handler attempt and preserve its provenance in context and logs.

**Context**

Snapshot and revalidate modes cannot expand origin authority. Service policy is a separately named capability and must never masquerade as user-derived scope.

**Affected files**

- `src/fastapi_mergen/core/policy.py`
- `src/fastapi_mergen/handlers/executor.py`
- `src/fastapi_mergen/core/principal.py`
- `tests/conformance/test_authority.py`
- `docs/concepts/authorization.md`

**Definition of Done**

- [ ] Snapshot mode enforces maximum age and intersection with route-allowed scopes.
- [ ] Revalidate mode calls the configured resolver per attempt and intersects current scopes with origin ceiling and route allowance.
- [ ] Service-policy mode resolves only pre-registered named capabilities and records user origin separately.
- [ ] Revocation, provider outage, missing service policy, and denied scope have documented terminal/retry behavior.
- [ ] No raw token is required or loaded from event/delivery rows.

### - [ ] M2.24 — Add core structured logging, metrics, and trace propagation

**Estimate:** 3 h  
**Depends on:** M2.13–M2.23

**Goal**

Expose operational state and causal lineage without leaking payloads, credentials, or secrets.

**Context**

Observability is part of delivery correctness: operators need claim, duration, retry, dead-letter, lease-loss, and queue-age signals. Cardinality must remain bounded.

**Affected files**

- `src/fastapi_mergen/observability/logging.py`
- `src/fastapi_mergen/observability/metrics.py`
- `src/fastapi_mergen/observability/tracing.py`
- `tests/security/test_observability_redaction.py`

**Definition of Done**

- [ ] Structured events include approved tenant/event/delivery/attempt/route/worker identifiers and outcome fields.
- [ ] Payloads, origin scopes, credentials, policy bodies, and error stack locals are excluded by default.
- [ ] Metrics cover due age, claims, outcomes, retries, dead rows, lease loss, renewals, and active work with bounded labels.
- [ ] Trace context is propagated when valid and ignored safely when malformed.

### - [ ] M2.25 — Implement `fastapi-mergen doctor` and schema compatibility checks

**Estimate:** 5 h  
**Depends on:** M2.08–M2.10, M2.24

**Goal**

Detect role, ownership, RLS, pool, search-path, grant, and schema-revision failures before serving production traffic.

**Context**

Many RLS failures are configuration failures rather than code failures. Diagnostics must run live probes as the actual runtime roles and return actionable, redacted results.

**Affected files**

- `src/fastapi_mergen/postgres/diagnostics.py`
- `src/fastapi_mergen/cli/main.py`
- `src/fastapi_mergen/cli/doctor.py`
- `tests/integration/test_doctor.py`
- `tests/security/test_doctor_misconfigurations.py`

**Definition of Done**

- [ ] Doctor checks superuser/owner/`BYPASSRLS`, RLS enabled/forced, expected policies, and schema revision.
- [ ] Live probes verify `USING`, `WITH CHECK`, missing-context denial, commit/rollback reset, and pool reuse.
- [ ] Relay denial on application schemas and unsafe writable search-path objects are tested.
- [ ] CLI exits non-zero for failed critical checks and offers machine-readable JSON plus human output.
- [ ] Output contains no passwords, DSNs with credentials, event payloads, or secret material.

### - [ ] M2.26 — Build reusable fixtures and the core conformance suites

**Estimate:** 7 h  
**Depends on:** M2.01–M2.25

**Goal**

Convert the Boundary Contract into a public, repeatable test suite covering atomicity, isolation, authority, delivery, lifecycle, and packaging.

**Context**

The conformance suite is part of the product wedge and will later test external adapters. It should be runnable against the built-in implementation and reusable by third parties.

**Affected files**

- `src/fastapi_mergen/conformance/`
- `src/fastapi_mergen/testing/`
- `tests/conformance/test_atomicity.py`
- `tests/conformance/test_isolation.py`
- `tests/conformance/test_authority.py`
- `tests/conformance/test_delivery.py`
- `tests/conformance/test_lifecycle.py`
- `tests/packaging/`

**Definition of Done**

- [ ] Every normative MDP guarantee has at least one positive and one negative test where meaningful.
- [ ] Fixtures create isolated tenants, app/relay sessions, deterministic clocks/randomness, and controllable sinks.
- [ ] Suite demonstrates rollback/no-effect, independent sibling delivery state, stale-token rejection, replay lineage, and cleanup.
- [ ] Tests are stable under randomized order and parallel execution.
- [ ] A documented third-party harness interface exists without exposing internal ORM models.

### - [ ] M2.27 — Complete the crash harness, invoicing vertical slice, alpha packaging, and design-partner gate

**Estimate:** 7 h  
**Depends on:** M2.01–M2.26

**Goal**

Demonstrate the complete core flow under controlled process failure and package it for limited external evaluation.

**Context**

The vertical slice must prove that application state and effect intent commit together, handlers execute tenant-safely, and documented duplicates occur without lost committed work.

**Affected files**

- `tests/chaos/harness.py`
- `tests/chaos/test_kill_matrix.py`
- `examples/invoicing/app/`
- `examples/invoicing/tests/test_vertical_slice.py`
- `docs/operations/relay.md`
- `docs/milestone-2-review.md`
- `CHANGELOG.md`

**Definition of Done**

- [ ] Kill matrix covers before commit, after commit/before claim, after claim/before execution, during execution, after effect/before finalization, during renewal, and during shutdown.
- [ ] No committed original delivery is lost; any duplicate is the documented same delivery with a new attempt.
- [ ] Two-tenant reference flow proves handler session, RLS, principal, and dependency isolation.
- [ ] Wheel installs into a clean environment, migrations apply, doctor passes, relay runs, and example tests succeed.
- [ ] Known alpha limitations are explicit, and at least one design partner records API/schema acceptance or concrete blocking feedback.

---

## M3 — Webhook Minimum Differentiated Product

**Duration:** 8–10 weeks  
**Estimated effort:** 80–110 hours  
**Release target:** `v0.2.0b1`, followed by `v0.2.0` after design-partner validation  

### Milestone goal

Add tenant-scoped outbound webhook subscriptions, encrypted/rotatable secrets, deterministic signed messages, an SSRF-safe transport, operational APIs, and webhook-specific conformance/chaos coverage.

### Milestone exit gate

- [ ] A design partner runs the end-to-end flow in serious staging or production-like conditions.
- [ ] Receiver success followed by relay crash produces multiple attempts and one effective consumer outcome.
- [ ] The SSRF suite blocks private, loopback, link-local, metadata, mapped-address, redirect, and DNS-rebinding cases.
- [ ] Secret rotation works with overlapping signatures and no plaintext-secret leakage.
- [ ] Pausing affects future route snapshotting without silently mutating committed deliveries.

### Work items

### - [ ] M3.01 — Define webhook subscription and secret domain contracts

**Estimate:** 4 h  
**Depends on:** M2 complete

**Goal**

Freeze subscription status, exact filters, endpoint identity, secret-set lifecycle, auto-pause semantics, and public service protocols.

**Context**

A subscription controls future route materialization; it is not a cancellation switch for already committed deliveries. Secret sets have independent lifecycle and must not expose plaintext after creation.

**Affected files**

- `src/fastapi_mergen/webhooks/models.py`
- `src/fastapi_mergen/webhooks/subscriptions.py`
- `src/fastapi_mergen/webhooks/secrets.py`
- `docs/adr/0006-webhook-subscriptions-and-secrets.md`
- `tests/unit/webhooks/test_models.py`

**Definition of Done**

- [ ] Subscription states are exactly active, paused, and disabled with legal transitions defined.
- [ ] Exact event-type filter, endpoint URL, retry profile, failure threshold, and stable secret-set ID are represented.
- [ ] Pause semantics explicitly affect new snapshots only; existing deliveries continue under their snapshot.
- [ ] Secret version states and active/retiring/revoked transitions are defined.
- [ ] Public protocols do not expose storage ciphertext shape or plaintext through read methods.

### - [ ] M3.02 — Add subscription and encrypted-secret schema, migrations, grants, and RLS

**Estimate:** 6 h  
**Depends on:** M3.01

**Goal**

Persist tenant-scoped subscriptions and encrypted secret versions with tenant-safe references and least-privilege policies.

**Context**

Request-role users need tenant-limited CRUD; relay needs read access to active subscription snapshots and encrypted secret versions, but not application tables or deletion of audit history.

**Affected files**

- `src/fastapi_mergen/webhooks/models.py`
- `src/fastapi_mergen/postgres/migrations/versions/0005_webhook_schema.py`
- `src/fastapi_mergen/postgres/migrations/versions/0006_webhook_rls.py`
- `tests/integration/webhooks/test_migrations.py`
- `tests/security/webhooks/test_webhook_rls.py`

**Definition of Done**

- [ ] Schema includes subscription, secret set, secret version, and auditable status/failure fields.
- [ ] All tenant relationships use composite tenant-safe foreign keys.
- [ ] Encrypted secret columns include algorithm, nonce, ciphertext, key ID, lifecycle state, and timestamps; no plaintext column exists.
- [ ] App and relay grants/policies pass positive and cross-tenant negative probes.
- [ ] Upgrade/downgrade and clean-wheel migration tests pass.

### - [ ] M3.03 — Implement subscription service and exact event-type matching

**Estimate:** 5 h  
**Depends on:** M3.01–M3.02

**Goal**

Provide tenant-safe subscription create/read/update/status operations and deterministic exact event matching for emission-time snapshots.

**Context**

Wildcard/filter DSLs are out of scope. Subscription queries execute inside the originating UoW so eligible destinations are snapshotted atomically with the application change.

**Affected files**

- `src/fastapi_mergen/webhooks/subscriptions.py`
- `src/fastapi_mergen/sqlalchemy/repository.py`
- `tests/integration/webhooks/test_subscriptions.py`
- `tests/conformance/webhooks/test_subscription_snapshotting.py`

**Definition of Done**

- [ ] CRUD requires tenant-bound app sessions and enforces optimistic/state validation.
- [ ] Only active subscriptions whose exact event-type set contains the emitted type are eligible.
- [ ] Paused/disabled subscriptions are excluded from new emissions without mutating old deliveries.
- [ ] Endpoint/filter/status changes are audit-attributed and affect only later emissions.
- [ ] Concurrent status change versus emission has a documented transaction/isolation outcome and a deterministic test.

### - [ ] M3.04 — Implement `SecretStore` and `MasterKeyProvider` protocols

**Estimate:** 5 h  
**Depends on:** M3.01

**Goal**

Separate secret lifecycle and encryption-key retrieval from database and deployment-specific implementations.

**Context**

The built-in database store is one implementation. The master key must come from environment/KMS/plugin code without entering PostgreSQL, logs, exceptions, or snapshots.

**Affected files**

- `src/fastapi_mergen/webhooks/secrets.py`
- `src/fastapi_mergen/core/protocols.py`
- `tests/unit/webhooks/test_secret_protocols.py`
- `docs/reference/secret-provider.md`

**Definition of Done**

- [ ] Protocols cover create, load-for-signing, rotate, retire, revoke, and metadata-only inspection.
- [ ] No read API returns plaintext except a narrowly scoped signing context or one-time creation response.
- [ ] Master-key provider returns keyed material by key ID and supports rotation without storing provider secrets.
- [ ] Secret-bearing objects have redacted `repr`/string behavior and explicit zeroization/bounded-lifetime limitations documented.
- [ ] Fake providers enable deterministic tests without weakening production interfaces.

### - [ ] M3.05 — Implement the AES-256-GCM database-backed secret store

**Estimate:** 6 h  
**Depends on:** M3.02, M3.04

**Goal**

Encrypt webhook signing secrets at rest with authenticated envelope encryption and strict redaction.

**Context**

Each endpoint receives a unique secret set. Ciphertext, nonce, algorithm, and key ID are stored; the master key remains outside PostgreSQL. Associated data binds ciphertext to tenant, secret-set, and version identity.

**Affected files**

- `src/fastapi_mergen/webhooks/secrets.py`
- `src/fastapi_mergen/webhooks/crypto.py`
- `tests/unit/webhooks/test_crypto.py`
- `tests/integration/webhooks/test_secret_store.py`
- `tests/security/webhooks/test_secret_redaction.py`

**Definition of Done**

- [ ] Encryption uses 256-bit keys, fresh nonces, authenticated associated data, and a reviewed cryptography library.
- [ ] Ciphertext cannot be swapped across tenant/secret-set/version without authentication failure.
- [ ] Wrong/missing key ID, corrupted ciphertext, and invalid tag fail safely without exposing plaintext.
- [ ] Plaintext is absent from SQL logs, structured logs, exceptions, fixtures, snapshots, and stored rows.
- [ ] Known-answer/round-trip tests and key-provider failure tests pass.

### - [ ] M3.06 — Implement zero-downtime secret rotation and revocation lifecycle

**Estimate:** 5 h  
**Depends on:** M3.05

**Goal**

Support overlapping active and retiring signatures, auditable activation, and explicit revocation without mutating delivery snapshots.

**Context**

The destination snapshot references a stable secret-set ID. Each attempt loads currently signable versions; body/message identity remains stable while attempt timestamp/signature may change.

**Affected files**

- `src/fastapi_mergen/webhooks/secrets.py`
- `src/fastapi_mergen/webhooks/signing.py`
- `tests/integration/webhooks/test_secret_rotation.py`
- `docs/operations/webhooks.md`

**Definition of Done**

- [ ] Rotation creates a new version, marks prior active version retiring, and supports a configured overlap window.
- [ ] Signing emits signatures for all permitted active/retiring versions in deterministic order.
- [ ] Revoked versions are never used for new attempts; destructive deletion requires separate retention rules.
- [ ] Lifecycle changes are tenant-scoped, authenticated, and audit logged.
- [ ] Concurrent rotation and delivery has a documented outcome and no plaintext leakage.

### - [ ] M3.07 — Materialize immutable webhook delivery snapshots during `emit()`

**Estimate:** 5 h  
**Depends on:** M3.03, M3.06

**Goal**

Create one independent webhook delivery per eligible subscription in the originating application transaction.

**Context**

The snapshot stores endpoint URL and secret-set identity, not plaintext secret. Later subscription changes do not alter original deliveries; pause only affects future matching.

**Affected files**

- `src/fastapi_mergen/webhooks/subscriptions.py`
- `src/fastapi_mergen/sqlalchemy/uow.py`
- `src/fastapi_mergen/sqlalchemy/repository.py`
- `tests/integration/webhooks/test_emit_fanout.py`

**Definition of Done**

- [ ] Each eligible subscription creates a unique original delivery with sink kind `webhook`.
- [ ] Destination key and unique index prevent duplicate original routes for one event/subscription/version.
- [ ] Snapshot contains normalized endpoint, subscription ID, secret-set ID, route/retry/policy versions, and no secret.
- [ ] One subscription snapshot failure rolls back application state, event, and all delivery intents.
- [ ] Later endpoint/filter/status/secret-version changes do not mutate committed snapshots.

### - [ ] M3.08 — Implement deterministic versioned webhook envelope serialization

**Estimate:** 4 h  
**Depends on:** M2.04, M3.07

**Goal**

Produce stable message bytes for one delivery across automatic retries and a new identity for manual replay.

**Context**

The exact signed bytes must be the exact transmitted bytes. Message ID maps to delivery identity; event ID remains causal identity. Retry timestamp/signature may vary without changing body bytes.

**Affected files**

- `src/fastapi_mergen/webhooks/serializer.py`
- `src/fastapi_mergen/webhooks/models.py`
- `tests/unit/webhooks/test_serializer.py`
- `tests/fixtures/webhook_envelopes/`

**Definition of Done**

- [ ] Envelope includes spec version, delivery message ID, event ID, type, schema version, tenant, occurred-at, and data.
- [ ] Canonical bytes remain identical across retries and supported Python versions.
- [ ] Manual replay produces a new message ID while retaining event lineage.
- [ ] Payload/body limit is enforced before signing or network access.
- [ ] Golden vectors detect accidental envelope or canonicalization changes.

### - [ ] M3.09 — Implement Standard Webhooks-compatible signing

**Estimate:** 4 h  
**Depends on:** M3.06, M3.08

**Goal**

Generate standard-compatible message ID, timestamp, and signature headers over the exact serialized bytes.

**Context**

The library should delegate cryptographic/signature format details to the Standard Webhooks implementation while controlling stable message identity, per-attempt timestamp, and rotation signatures.

**Affected files**

- `src/fastapi_mergen/webhooks/signing.py`
- `tests/unit/webhooks/test_signing.py`
- `tests/conformance/webhooks/test_standard_vectors.py`
- `examples/webhook_receiver/verify.py`

**Definition of Done**

- [ ] Official/known Standard Webhooks vectors pass where applicable.
- [ ] Header message ID is stable for automatic retry and new for replay.
- [ ] The timestamp is generated per attempt from an injected/testable clock.
- [ ] Multiple active/retiring signatures are encoded and verified correctly.
- [ ] A byte mutation after signing is detected by the receiver test.

### - [ ] M3.10 — Implement webhook URL parsing, normalization, and static policy validation

**Estimate:** 4 h  
**Depends on:** M3.01

**Goal**

Reject malformed or disallowed endpoint URLs before persistence and again before each attempt.

**Context**

Static parsing is necessary but not sufficient for SSRF. It establishes HTTPS, authority, port, credential, fragment, hostname/IDNA, and explicit deployment-policy rules before DNS resolution.

**Affected files**

- `src/fastapi_mergen/webhooks/transport.py`
- `src/fastapi_mergen/webhooks/url_policy.py`
- `tests/unit/webhooks/test_url_policy.py`
- `tests/security/webhooks/test_url_edge_cases.py`

**Definition of Done**

- [ ] Production mode requires HTTPS and rejects userinfo, fragments, invalid ports, empty hosts, ambiguous encodings, and prohibited schemes.
- [ ] Hostname is normalized with IDNA and retained separately from resolved IP.
- [ ] IPv4/IPv6 literals follow the same address policy as DNS results.
- [ ] Validation is idempotent and outputs a typed normalized endpoint rather than a raw string.
- [ ] Parser corpus includes Unicode, mixed encoding, trailing-dot, mapped-address, and authority-confusion cases.

### - [ ] M3.11 — Implement per-attempt DNS resolution and destination-IP policy

**Estimate:** 6 h  
**Depends on:** M3.10

**Goal**

Resolve every attempt, classify every A/AAAA result, and reject endpoints whose selected candidates violate the allowed routing policy.

**Context**

A hostname can resolve differently between validation and connection. Mergen must validate the actual IP it will connect to and explicitly cover private, loopback, link-local, multicast, reserved, unspecified, metadata, and IPv4-mapped IPv6 cases.

**Affected files**

- `src/fastapi_mergen/webhooks/dns.py`
- `src/fastapi_mergen/webhooks/url_policy.py`
- `tests/unit/webhooks/test_ip_policy.py`
- `tests/security/webhooks/test_dns_rebinding.py`

**Definition of Done**

- [ ] Resolver returns normalized candidate records with family, TTL/metadata where available, and deterministic selection policy.
- [ ] Every candidate is checked against the configured global-routing/special-range policy.
- [ ] IPv4-mapped IPv6 is normalized and cannot bypass IPv4 restrictions.
- [ ] Cloud metadata and special-use defense-in-depth deny rules are explicit and tested.
- [ ] DNS-rebinding harness proves the connection layer uses the validated selected IP rather than re-resolving the hostname.

### - [ ] M3.12 — Implement explicit-IP HTTPX transport with original-host TLS SNI and authority

**Estimate:** 8 h  
**Depends on:** M3.10–M3.11

**Goal**

Connect to the exact validated IP while preserving certificate validation and HTTP routing for the original hostname.

**Context**

The transport must eliminate the validation/connect DNS time-of-check gap. It may use a custom HTTPX/httpcore transport or a carefully bounded extension mechanism, but the behavior must be proven with local TLS fixtures.

**Affected files**

- `src/fastapi_mergen/webhooks/transport.py`
- `src/fastapi_mergen/webhooks/httpcore_transport.py`
- `tests/integration/webhooks/test_explicit_ip_transport.py`
- `tests/security/webhooks/test_tls_sni_and_host.py`
- `tests/fixtures/certs/`

**Definition of Done**

- [ ] TCP connects to the selected validated IP and never performs a second hostname DNS lookup.
- [ ] TLS certificate verification uses the original normalized hostname as SNI/server name.
- [ ] HTTP authority/Host remains the original hostname and permitted port.
- [ ] IPv4 and IPv6 endpoints work in the integration harness.
- [ ] Certificate mismatch, invalid chain, SNI mismatch, and connect-to-blocked-IP fail closed.
- [ ] Transport behavior is isolated behind a protocol so HTTPX internals can be upgraded without public API changes.

### - [ ] M3.13 — Enforce redirect, proxy, timeout, byte, and concurrency policies

**Estimate:** 4 h  
**Depends on:** M3.12

**Goal**

Bound every network attempt and prevent redirects or deployment proxies from bypassing endpoint validation.

**Context**

Redirects are disabled by default. An enabled redirect is a new destination requiring full parsing, DNS validation, and explicit-IP connection. Proxy mode must be opt-in and documented as a changed trust boundary.

**Affected files**

- `src/fastapi_mergen/webhooks/transport.py`
- `src/fastapi_mergen/webhooks/config.py`
- `tests/security/webhooks/test_redirects.py`
- `tests/integration/webhooks/test_transport_limits.py`

**Definition of Done**

- [ ] Redirects are off by default; each permitted redirect re-enters the complete validation pipeline and is hop-limited.
- [ ] Connect/read/write/pool/total timeouts are independently configurable and bounded.
- [ ] Request and response body limits abort safely without storing response bodies.
- [ ] Global, tenant, and destination concurrency limits are enforced.
- [ ] Trusted egress proxy mode is explicit, mutually consistent with direct mode, and documented as shifting DNS/IP enforcement responsibility.

### - [ ] M3.14 — Implement webhook outcome classification and `Retry-After` handling

**Estimate:** 5 h  
**Depends on:** M2.20, M3.12–M3.13

**Goal**

Map HTTP/transport/security outcomes into succeeded, retryable, or terminal delivery results with bounded retry timing.

**Context**

Classification must be deterministic and configurable only through safe policy surfaces. Security-policy rejection and TLS validation failure are terminal; transient network/server failures are generally retryable.

**Affected files**

- `src/fastapi_mergen/webhooks/sink.py`
- `src/fastapi_mergen/webhooks/retry.py`
- `tests/unit/webhooks/test_classification.py`
- `tests/integration/webhooks/test_retry_after.py`

**Definition of Done**

- [ ] Default status/exception classification matches documented retryable and terminal sets.
- [ ] `Retry-After` supports valid delay/date forms, ignores malformed values safely, and is clamped to policy/deadline.
- [ ] Security-policy, certificate, oversize, and missing-secret failures are terminal unless a narrowly documented operator action repairs them.
- [ ] Only bounded status code, duration, byte counts, remote request ID, and sanitized summary are persisted.
- [ ] Classification tests are table-driven and deterministic.

### - [ ] M3.15 — Integrate the webhook sink into relay execution and finalization

**Estimate:** 5 h  
**Depends on:** M3.07–M3.14

**Goal**

Execute snapshotted webhook deliveries through serialization, secret loading, signing, safe transport, and core finalization semantics.

**Context**

The sink receives immutable event/delivery snapshots and the current lease context. It cannot alter destination or policy snapshots and must preserve stable body/message identity across retries.

**Affected files**

- `src/fastapi_mergen/webhooks/sink.py`
- `src/fastapi_mergen/postgres/relay.py`
- `src/fastapi_mergen/api.py`
- `tests/integration/webhooks/test_sink_end_to_end.py`

**Definition of Done**

- [ ] Relay dispatch selects webhook sink by snapshotted sink kind without importing optional dependencies in base-only installations.
- [ ] Each attempt loads signable secret versions, serializes stable bytes, signs, sends once, and returns a typed outcome.
- [ ] Lease renewal/timeout integrates with network attempt boundaries.
- [ ] Automatic retry sends the same message ID/body; replay sends a new message ID.
- [ ] One webhook delivery failure does not change handler or sibling webhook deliveries.

### - [ ] M3.16 — Implement subscription failure counters and auto-pause

**Estimate:** 4 h  
**Depends on:** M3.03, M3.15

**Goal**

Protect systems from continuously failing endpoints while preserving committed-delivery semantics.

**Context**

Auto-pause prevents future delivery snapshots after a threshold. It does not silently cancel existing delivery intents. Counter updates need race-safe semantics under concurrent deliveries.

**Affected files**

- `src/fastapi_mergen/webhooks/subscriptions.py`
- `src/fastapi_mergen/webhooks/sink.py`
- `tests/integration/webhooks/test_auto_pause.py`
- `docs/operations/webhooks.md`

**Definition of Done**

- [ ] Success resets consecutive failures; classified failure increments them atomically.
- [ ] Threshold crossing changes active to paused once and emits an audit/metric event.
- [ ] Concurrent attempts cannot lose increments or repeatedly emit pause events.
- [ ] Paused subscription is excluded from new snapshotting while existing delivery rows remain unchanged.
- [ ] Reactivation is explicit, tenant-authorized, and audit attributed.

### - [ ] M3.17 — Implement tenant-scoped webhook operational APIs and CLI operations

**Estimate:** 6 h  
**Depends on:** M3.02–M3.16

**Goal**

Expose safe subscription management, delivery inspection, dead-letter listing, replay, and status operations without creating an admin UI.

**Context**

Operational APIs must be tenant-bound through the same app role/UoW discipline. Replay is a new delivery with lineage and requires an explicit reason and authorized subject.

**Affected files**

- `src/fastapi_mergen/webhooks/api.py`
- `src/fastapi_mergen/cli/webhooks.py`
- `src/fastapi_mergen/sqlalchemy/repository.py`
- `tests/integration/webhooks/test_api.py`
- `tests/security/webhooks/test_api_tenant_isolation.py`

**Definition of Done**

- [ ] API supports create/list/update/pause/reactivate subscriptions, list deliveries/attempts, list dead rows, and replay.
- [ ] Pagination is stable and bounded; filtering cannot escape tenant scope.
- [ ] Secret is returned only once at creation/rotation where configured; later reads return metadata only.
- [ ] Replay creates a new delivery/message ID with `replay_of`, reason, and replaying subject; original row remains terminal.
- [ ] There is no MDP endpoint that mutates a terminal delivery back to pending or cancels an existing delivery.

### - [ ] M3.18 — Add webhook metrics, logs, audit events, and redaction controls

**Estimate:** 4 h  
**Depends on:** M3.15–M3.17

**Goal**

Make endpoint health, retries, latency, auto-pause, rotation, and replay observable without exposing sensitive content.

**Context**

Webhook URLs may themselves be sensitive and payloads often contain customer data. Logs and metric labels need explicit allowlists and cardinality controls.

**Affected files**

- `src/fastapi_mergen/observability/webhooks.py`
- `src/fastapi_mergen/webhooks/audit.py`
- `tests/security/webhooks/test_observability_redaction.py`
- `docs/operations/webhooks.md`

**Definition of Done**

- [ ] Metrics cover attempts/outcomes/latency/due age/dead/paused/rotation/replay with bounded labels.
- [ ] Default logs omit payload, signatures, secrets, full response bodies, and URL query strings.
- [ ] Endpoint logging uses a documented redacted/hashed representation.
- [ ] Secret rotation, pause/reactivate, replay, and configuration changes create tenant-attributed audit records.
- [ ] Automated secret/payload canary tests fail when sensitive values appear in captured logs or metrics.

### - [ ] M3.19 — Build the durable deduplicating webhook receiver example

**Estimate:** 4 h  
**Depends on:** M3.08–M3.15

**Goal**

Demonstrate Standard Webhooks verification and effectively-once consumer behavior using the stable message ID.

**Context**

The sender guarantees at-least-once delivery, not exactly once. The example must visibly process duplicate attempts once while retaining request/attempt audit information.

**Affected files**

- `examples/webhook_receiver/main.py`
- `examples/webhook_receiver/models.py`
- `examples/webhook_receiver/verify.py`
- `examples/webhook_receiver/tests/test_deduplication.py`
- `docs/examples/deduplicating-receiver.md`

**Definition of Done**

- [ ] Receiver verifies timestamp/signature against active and retiring keys before parsing business data.
- [ ] A durable unique constraint on message ID gates the business effect.
- [ ] Duplicate requests return a documented success response without repeating the effect.
- [ ] Manual replay with a new message ID is intentionally processed again.
- [ ] Example explains clock-skew, signature rotation, transaction boundaries, and retention of dedupe keys.

### - [ ] M3.20 — Complete webhook security, conformance, and chaos suites

**Estimate:** 9 h  
**Depends on:** M3.01–M3.19

**Goal**

Prove signing, stable identities, transport controls, failure semantics, duplicate behavior, secret safety, and subscription isolation under adversarial conditions.

**Context**

This suite is the release gate for the differentiated product. It must include real DNS/TLS/local-network fixtures where mocks would hide resolver/connection behavior.

**Affected files**

- `tests/conformance/webhooks/`
- `tests/security/webhooks/`
- `tests/chaos/webhooks/`
- `tests/fixtures/dns/`
- `tests/fixtures/certs/`
- `src/fastapi_mergen/conformance/webhooks.py`

**Definition of Done**

- [ ] Standard signing vectors, exact signed/sent bytes, rotation overlap, and stable retry/new replay IDs pass.
- [ ] SSRF cases cover loopback, RFC1918/ULA, link-local, multicast, unspecified, reserved, metadata, mapped IPv6, redirect, userinfo, malformed authority, and DNS rebinding.
- [ ] Crash after receiver success and before finalization yields duplicate attempts but one effective receiver outcome.
- [ ] Secret corruption, key-provider outage, receiver timeout, response oversize, malformed `Retry-After`, and concurrent auto-pause are tested.
- [ ] Canary payload/secret values never appear in database attempt rows, logs, metrics, exceptions, or API responses.
- [ ] Suite passes from built wheel on PostgreSQL 16 and 18.

### - [ ] M3.21 — Finish the production-style demo, operations documentation, beta release, and design-partner validation

**Estimate:** 7 h  
**Depends on:** M3.01–M3.20

**Goal**

Package the complete tenant-safe webhook flow for external evaluation and make operations/failure behavior understandable without reading source code.

**Context**

The MDP is not complete until another team can migrate, configure roles, run doctor, start relay, register a webhook, observe retries, rotate a secret, replay a dead delivery, and deduplicate duplicates.

**Affected files**

- `examples/invoicing/`
- `examples/webhook_receiver/`
- `docs/operations/webhooks.md`
- `docs/operations/relay.md`
- `docs/operations/retries-and-replay.md`
- `docs/operations/retention.md`
- `docs/milestone-3-review.md`
- `README.md`
- `CHANGELOG.md`

**Definition of Done**

- [ ] One documented command sequence runs app, PostgreSQL, relay, and receiver and demonstrates success, failure, retry, crash duplicate, rotation, pause, dead-letter, and replay.
- [ ] Runbooks cover migrations, role setup, backups, retention, relay sizing, health checks, incidents, key rotation, and rollback limitations.
- [ ] `v0.2.0b1` wheel/sdist pass all package, migration, core, webhook, security, and chaos gates.
- [ ] At least one design partner records results from serious staging or production-like use and all critical findings are resolved or explicitly block `v0.2.0`.
- [ ] Public README makes at-least-once semantics, consumer dedupe requirement, PostgreSQL/async-only scope, and security limitations prominent.

---

## Final release-gate checklist after Milestone 3

- [ ] All Milestone 1–3 task-level DoD checkboxes are complete or an approved ADR records the deliberate exception.
- [ ] The published wheel and sdist pass the same core, migration, security, and webhook tests as the source checkout.
- [ ] PostgreSQL 16 and 18 integration jobs pass; supported Python and dependency jobs pass.
- [ ] The MDP demo proves atomic commit, tenant isolation, handler isolation, webhook retry, duplicate dedupe, secret rotation, auto-pause, dead-letter, and replay.
- [ ] Doctor passes in the reference deployment and fails every intentionally unsafe role/RLS/grant configuration.
- [ ] No raw secret or canary payload is found in logs, metrics, exceptions, attempt rows, or API responses.
- [ ] A design partner has completed serious staging or production-like evaluation.
- [ ] README and operations docs state the supported matrix, at-least-once semantics, consumer-dedupe requirement, and security limitations prominently.
- [ ] Post-MDP work remains gated by external demand; no queue, idempotency, or MCP implementation is started merely to fill the roadmap.

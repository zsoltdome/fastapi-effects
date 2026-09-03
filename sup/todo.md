# FastAPI-Mergen — Continuation Technical TODO

**Date:** 2026-08-27
**Companion:** `plan.md`
**Starting point:** recoverable `0.6.0a1` assurance baseline
**Scope:** Milestones 8–13, ending at a gated `1.0.0`

## How to use this checklist

- Complete tasks in dependency order unless a task explicitly permits parallel work.
- Check a task heading only when every Definition of Done item is complete.
- A reference-driver result never completes a production-runtime task; the real adapter must exercise the real infrastructure path.
- Any change to a frozen invariant, public guarantee, identity rule, state transition, or trust boundary requires an ADR before implementation.
- File paths are intended targets. New modules may be split further when one file would otherwise mix trust boundaries or become difficult to review.
- Release tasks include documentation, migration, clean-artifact, and extracted-archive behavior; local unit success alone is insufficient.

## Preserved baseline

- [x] Milestone 1 repository, packaging, API spike, and normative design are preserved.
- [x] Boundary Contract v1 and Milestone 7 conformance/assurance suite are implemented.
- [x] Reference driver, fault oracle, evidence schemas, reporters, and archived verification are implemented.
- [x] Milestone 2–6 runtime behavior exists in the cumulative repository. **Implemented anew during M8–M12.**
- [x] Live PostgreSQL 16/18, Ruff, mypy, Twine, and resolver-lock gates are mandatory and passing locally.

## Cross-milestone non-negotiable rules

- [x] No generic exactly-once claim: local publication is atomic; external delivery is at least once.
- [x] No handler, broker, DNS, TLS, or HTTP I/O while claim locks are held.
- [x] No raw bearer token, cookie, API key, session token, plaintext webhook secret, or caller idempotency key in durable rows or default evidence.
- [x] No runtime table ownership, superuser credential, or `BYPASSRLS` role.
- [x] Relay/control-plane sessions never enter application handler code.
- [x] Automatic retry retains stable delivery/message identity; manual replay creates a new linked delivery.
- [x] Polling remains the correctness path through v1; notification may only be a wake-up optimization.
- [x] Every advertised capability is certified through a real implementation adapter, not only the reference driver.
- [x] One distribution and one import root remain in force through v1.
- [ ] All Git authors and committers are `mergen-institute`; subjects contain 3–7 words; every milestone branch is merged into `main`.

---

## M8 — Cumulative core runtime restoration

**Target:** `0.7.0a1`
**Estimated total:** 100–145 hours
**Milestone exit:** real PostgreSQL runtime certifies `core`, `delivery`, and `security`

### - [x] M8.01 — Record the truthful cumulative baseline

**Estimate:** 3–5 h
**Depends on:** None

**Goal**

Create an explicit development baseline that distinguishes implemented assurance code from absent runtime code and prevents future release notes from implying false continuity.

**Context**

The current repository is valid as a Milestone 1 plus Milestone 7 assurance baseline. Continuing safely requires preserving that provenance while making the next implementation history transparent.

**Affected files**

- `README.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_REPORT_M7.md`
- `docs/planning/runtime-recovery.md`
- `docs/adr/ADR-006-runtime-recovery.md`

**Definition of Done**

- [x] The current Git commit is recorded as the assurance baseline and remains reachable from `main`.
- [x] Documentation states that Milestone 2–6 runtime source was unavailable and will be newly implemented rather than reconstructed historically.
- [x] README feature tables distinguish `implemented`, `reference-only`, and `planned` capabilities.
- [x] No public metadata or release note describes `0.6.0a1` as a production runtime.
- [x] A repository test fails when an advertised runtime capability still resolves to a Milestone 1 stub.

### - [x] M8.02 — Restore the reproducible quality toolchain

**Estimate:** 6–9 h
**Depends on:** M8.01

**Goal**

Make dependency resolution, formatting, linting, typing, package checks, and supported PostgreSQL services reproducible before security-critical runtime code grows.

**Context**

The Milestone 7 archive reported Ruff, mypy, Twine, and `uv.lock` as not run. These must become mandatory gates rather than optional evidence for the runtime line.

**Affected files**

- `pyproject.toml`
- `uv.lock`
- `scripts/check.py`
- `compose.yaml`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `CONTRIBUTING.md`

**Definition of Done**

- [x] `uv lock` produces a committed lockfile and `uv lock --check` passes from a clean checkout.
- [x] Ruff lint and format checks pass over `src`, `tests`, `examples`, and `scripts`.
- [x] Strict mypy passes for the public runtime and conformance packages.
- [x] Twine validates both wheel and sdist.
- [x] CI supplies PostgreSQL 16 and 18 and runs integration tests with explicit DSNs.
- [x] One local command reproduces the mandatory milestone gate.

### - [x] M8.03 — Freeze runtime APIs and schema decisions

**Estimate:** 5–8 h
**Depends on:** M8.01–M8.02

**Goal**

Translate the normative design into accepted ADRs and concrete public protocols before implementing persistence and concurrency.

**Context**

The API spike and planning documents contain the intended transaction, role, route, dedupe, replay, and lease semantics. Implementation should not silently choose different rules file by file.

**Affected files**

- `docs/adr/ADR-007-runtime-public-api.md`
- `docs/adr/ADR-008-schema-and-identity.md`
- `docs/adr/ADR-009-roles-and-rls.md`
- `docs/adr/ADR-010-leases-and-replay.md`
- `docs/reference/runtime-api.md`
- `src/fastapi_mergen/core/protocols.py`

**Definition of Done**

- [x] ADRs define event, delivery, attempt, replay, dedupe, and schema-revision identity.
- [x] The outer-transaction ownership rule and rejection of implicit active transactions are explicit.
- [x] The migration-owner, application, and relay role boundaries are fixed.
- [x] The public store, clock, random, authorization, session, and metrics protocols are typed and documented.
- [x] The Boundary Contract v1 requires no breaking change; any needed extension is additive and versioned.

### - [x] M8.04 — Implement canonical payload and identity primitives

**Estimate:** 7–10 h
**Depends on:** M8.03

**Goal**

Provide deterministic, bounded serialization and stable identity helpers used by event dedupe, delivery, replay, and conformance evidence.

**Context**

Payload equality and dedupe must not depend on Python dictionary ordering, ORM serialization, non-finite floats, or process-specific representations.

**Affected files**

- `src/fastapi_mergen/sqlalchemy/canonical.py`
- `src/fastapi_mergen/core/event.py`
- `src/fastapi_mergen/core/identity.py`
- `tests/unit/test_canonical_payloads.py`
- `tests/security/test_payload_bounds.py`

**Definition of Done**

- [x] Canonical JSON rejects non-finite numbers, duplicate semantic keys, unsupported values, and payloads above the configured limit.
- [x] Payload SHA-256 is computed over versioned canonical bytes.
- [x] UUID generation is injectable and does not imply ordering unless explicitly guaranteed.
- [x] Dedupe namespace/key, trace context, correlation, and causation identifiers have bounded validation.
- [x] Test vectors are stable across supported Python versions.

### - [x] M8.05 — Complete principal and context lifecycle

**Estimate:** 6–9 h
**Depends on:** M8.03

**Goal**

Turn the principal model into a durable, serializable, secret-minimizing envelope and implement leak-safe runtime binding.

**Context**

A `ContextVar` is ergonomic process state, not the durable boundary. The runtime needs explicit envelope conversion plus guaranteed reset on success, failure, and cancellation.

**Affected files**

- `src/fastapi_mergen/core/principal.py`
- `src/fastapi_mergen/core/context.py`
- `src/fastapi_mergen/core/protocols.py`
- `tests/unit/test_principal_envelope.py`
- `tests/security/test_context_cleanup.py`

**Definition of Done**

- [x] Principal serialization round-trips tenant, subject, actor, client, scopes, timestamps, and opaque credential reference.
- [x] Raw credential-like fields are rejected by envelope construction.
- [x] Context binding returns a reset token and always resets in `finally`.
- [x] Sequential and concurrent tenant tests prove no context leakage.
- [x] Public `repr` and errors reveal no secret-bearing metadata.

### - [x] M8.06 — Implement event delivery and attempt models

**Estimate:** 7–10 h
**Depends on:** M8.03–M8.05

**Goal**

Create immutable domain records for event intent, independently retryable deliveries, and append-only attempts.

**Context**

One outbox row cannot represent fan-out. The domain model must separate immutable origin facts from per-destination state and per-attempt observations.

**Affected files**

- `src/fastapi_mergen/core/delivery.py`
- `src/fastapi_mergen/core/event.py`
- `src/fastapi_mergen/core/retry.py`
- `src/fastapi_mergen/errors.py`
- `tests/unit/test_delivery_models.py`

**Definition of Done**

- [x] Event records contain a principal envelope, typed event identity, canonical payload hash, and causal lineage.
- [x] Delivery records contain immutable route/destination/policy snapshots and mutable state only where specified.
- [x] Attempt records are append-only and distinguish started, succeeded, retryable, terminal, abandoned, and lease-lost outcomes.
- [x] Automatic retry and manual replay identities follow the Boundary Contract.
- [x] Impossible states are rejected at model construction and later by database constraints.

### - [x] M8.07 — Complete exact route and policy snapshotting

**Estimate:** 6–9 h
**Depends on:** M8.03–M8.06

**Goal**

Make startup route registration deterministic and turn each route into an immutable delivery specification at emission time.

**Context**

Pending work must not change when Python functions, authorization rules, retry profiles, or destinations change after an event commits.

**Affected files**

- `src/fastapi_mergen/core/routing.py`
- `src/fastapi_mergen/core/policy.py`
- `src/fastapi_mergen/handlers/registry.py`
- `tests/unit/test_route_snapshots.py`
- `docs/reference/routing.md`

**Definition of Done**

- [x] Exact event-type matching is deterministic and wildcard routing remains absent.
- [x] Duplicate route key/version, handler mismatch, downgrade, and post-freeze registration fail startup.
- [x] Snapshot, revalidate, and service-policy configuration is fully resolved before registry freeze.
- [x] Delivery specifications contain JSON-safe immutable route, destination, retry, and authority snapshots.
- [x] Later route edits do not alter persisted delivery intent in integration tests.

### - [x] M8.08 — Add SQLAlchemy runtime mappings

**Estimate:** 8–12 h
**Depends on:** M8.04–M8.07

**Goal**

Map the event, delivery, attempt, and schema-revision records to explicit async SQLAlchemy 2.x models without leaking ORM objects into the public domain API.

**Context**

Persistence models must mirror database constraints and tenant-safe composite relationships while keeping typed DTOs and domain records independent from SQLAlchemy internals.

**Affected files**

- `src/fastapi_mergen/sqlalchemy/models.py`
- `src/fastapi_mergen/sqlalchemy/repository.py`
- `src/fastapi_mergen/sqlalchemy/__init__.py`
- `tests/unit/test_sqlalchemy_mappings.py`

**Definition of Done**

- [x] All Mergen tables live in the `fastapi_mergen` schema and include `tenant_id` where required.
- [x] Composite foreign keys include tenant identity.
- [x] No callable, session, raw credential, or plaintext secret is persisted.
- [x] ORM-to-domain conversion returns detached immutable records.
- [x] Metadata naming conventions make generated constraints and indexes deterministic.

### - [x] M8.09 — Create the base PostgreSQL migration

**Estimate:** 10–14 h
**Depends on:** M8.08

**Goal**

Create an Alembic migration that installs schema objects, constraints, indexes, helper functions, ownership, grants, and downgrade behavior.

**Context**

The runtime cannot rely on ORM metadata alone because roles, forced RLS, policies, helper functions, and secure ownership are first-class parts of the correctness model.

**Affected files**

- `src/fastapi_mergen/postgres/migrations/env.py`
- `src/fastapi_mergen/postgres/migrations/versions/0001_core_runtime.py`
- `src/fastapi_mergen/postgres/roles.py`
- `src/fastapi_mergen/postgres/rls.py`
- `tests/integration/test_core_migration.py`

**Definition of Done**

- [x] Upgrade creates schema revision, event, delivery, and attempt tables with documented constraints and indexes.
- [x] Migration owner, application role, and relay role have exact ownership and grants.
- [x] RLS is enabled and forced; application policies contain both `USING` and `WITH CHECK`.
- [x] Helper functions use fixed safe `search_path` and revoke unsafe public execution.
- [x] Downgrade removes only Mergen-owned objects in dependency-safe order.
- [x] Upgrade/downgrade passes on PostgreSQL 16 and 18.

### - [x] M8.10 — Implement live schema and role diagnostics

**Estimate:** 7–10 h
**Depends on:** M8.09

**Goal**

Turn `fastapi-mergen doctor` and schema checks into live probes that detect unsafe role, ownership, RLS, grant, search-path, and pooled-context configuration.

**Context**

DDL text can look correct while deployment credentials or ownership make RLS ineffective. Diagnostics must test configured roles rather than infer safety from source files.

**Affected files**

- `src/fastapi_mergen/postgres/diagnostics.py`
- `src/fastapi_mergen/cli/doctor.py`
- `src/fastapi_mergen/cli/main.py`
- `tests/integration/test_doctor.py`
- `docs/operations/roles-and-rls.md`

**Definition of Done**

- [x] Doctor checks superuser, `BYPASSRLS`, table ownership, RLS enabled/forced, policies, grants, and schema revision.
- [x] Live probes prove cross-tenant denial and missing-context default denial.
- [x] Commit, rollback, and pooled-connection reuse remove transaction-local tenant and subject settings.
- [x] Relay credentials are denied access to configured application tables.
- [x] Output is bounded, actionable, and excludes credentials or DSNs.

### - [x] M8.11 — Implement event persistence and dedupe

**Estimate:** 8–12 h
**Depends on:** M8.08–M8.10

**Goal**

Implement atomic event insertion, tenant-scoped dedupe, compatible reuse, and explicit payload-conflict behavior.

**Context**

Concurrent emissions must converge to one immutable event and one original delivery set without re-routing a duplicate through a changed registry.

**Affected files**

- `src/fastapi_mergen/postgres/store.py`
- `src/fastapi_mergen/sqlalchemy/repository.py`
- `src/fastapi_mergen/errors.py`
- `tests/integration/test_event_persistence.py`
- `tests/chaos/test_dedupe_races.py`

**Definition of Done**

- [x] A new dedupe identity inserts one event; a compatible duplicate returns the first committed event.
- [x] A different event type, schema version, or payload hash for the same identity raises `DedupeConflict`.
- [x] Concurrent no-row races converge without transaction-wide failure.
- [x] Duplicate reuse never creates a second original delivery set or refreshes snapshots.
- [x] The first committed principal and causal lineage remain authoritative.

### - [x] M8.12 — Implement the explicit SQLAlchemy unit of work

**Estimate:** 8–12 h
**Depends on:** M8.05, M8.08–M8.11

**Goal**

Replace the fail-closed UoW stub with explicit outer transaction ownership, tenant binding, atomic emission, and guaranteed cleanup.

**Context**

FastAPI dependencies and SQLAlchemy autobegin can make transaction ownership ambiguous. The MDP requires Mergen to own the outer transaction and fail before application SQL when that contract is violated.

**Affected files**

- `src/fastapi_mergen/sqlalchemy/uow.py`
- `src/fastapi_mergen/api.py`
- `src/fastapi_mergen/sqlalchemy/__init__.py`
- `tests/unit/test_uow_lifecycle.py`
- `tests/integration/test_uow_atomicity.py`

**Definition of Done**

- [x] UoW entry rejects an already active transaction and nested Mergen UoWs.
- [x] Tenant and subject settings are bound transaction-locally before application SQL.
- [x] `emit()` is unavailable outside the active UoW and uses the same session/transaction as business writes.
- [x] Successful exit commits business rows, event, and original deliveries; exception exit rolls all back.
- [x] Context tokens and session metadata reset after success, failure, cancellation, and entry failure.

### - [x] M8.13 — Implement atomic delivery fanout

**Estimate:** 7–10 h
**Depends on:** M8.07, M8.11–M8.12

**Goal**

Create one independent original delivery for every frozen route specification inside the originating transaction.

**Context**

Fan-out correctness requires all original intent rows to commit with the business operation while preserving independent subsequent state.

**Affected files**

- `src/fastapi_mergen/postgres/store.py`
- `src/fastapi_mergen/sqlalchemy/uow.py`
- `src/fastapi_mergen/core/routing.py`
- `tests/integration/test_atomic_fanout.py`

**Definition of Done**

- [x] New events insert every original route delivery before commit.
- [x] One destination's later failure cannot modify another delivery row.
- [x] Original delivery uniqueness prevents duplicate route/destination rows.
- [x] A failure while inserting any original delivery rolls back the business row and event.
- [x] Route, policy, and destination snapshots are byte-stable after commit.

### - [x] M8.14 — Implement lease claims and fenced finalization

**Estimate:** 10–14 h
**Depends on:** M8.08–M8.13

**Goal**

Implement short claim transactions, append-only attempt creation, lease-token fencing, retry scheduling, and terminal finalization.

**Context**

The relay must coordinate concurrent workers without holding locks during execution and without allowing stale workers to acknowledge reclaimed work.

**Affected files**

- `src/fastapi_mergen/postgres/leasing.py`
- `src/fastapi_mergen/core/delivery.py`
- `src/fastapi_mergen/core/retry.py`
- `tests/integration/test_delivery_leases.py`
- `tests/chaos/test_stale_finalization.py`

**Definition of Done**

- [x] Claim uses `FOR UPDATE SKIP LOCKED`, assigns a fresh token, increments attempts-started, inserts an attempt, and commits before I/O.
- [x] Finalization succeeds only for matching delivery state and lease token.
- [x] Success, retryable failure, and terminal failure update attempt and delivery atomically.
- [x] Full-jitter backoff and deadlines are deterministic under injected clock/random sources.
- [x] Concurrent workers cannot claim the same active delivery or overwrite newer state.

### - [x] M8.15 — Implement reconciliation and the polling relay

**Estimate:** 10–14 h
**Depends on:** M8.14

**Goal**

Add expired-lease reconciliation, bounded per-tenant fairness, worker concurrency, graceful shutdown, and polling-based execution.

**Context**

Polling is the correctness path. Recovery must tolerate crashes at each boundary while preventing unbounded tenant starvation and resource leakage.

**Affected files**

- `src/fastapi_mergen/postgres/relay.py`
- `src/fastapi_mergen/postgres/leasing.py`
- `src/fastapi_mergen/cli/relay.py`
- `tests/integration/test_relay_fairness.py`
- `tests/chaos/test_relay_crash_matrix.py`
- `docs/operations/relay.md`

**Definition of Done**

- [x] Expired leases become reclaimable with a new token and the prior open attempt becomes abandoned or lease-lost.
- [x] Claim loops enforce batch, per-tenant, and global concurrency bounds.
- [x] No sink execution or network I/O occurs while claim locks are held.
- [x] Shutdown stops claims first, drains or cancels active work according to policy, and closes sessions cleanly.
- [x] Crash tests show no lost committed delivery at every documented boundary.

The polling relay caps each claim transaction at `min(batch_size, concurrency)`, so a
lease is never queued behind the relay's own execution limit after its expiry clock has
already started. An integration probe asserts that excess work remains pending.

### - [x] M8.16 — Implement handler execution and authorization

**Estimate:** 10–14 h
**Depends on:** M8.05–M8.07, M8.12–M8.15

**Goal**

Execute in-process handlers under explicit snapshot, revalidate, or service-policy authority using a fresh tenant-bound application session.

**Context**

The relay session is cross-tenant control-plane authority and must never become the handler's application session. Authority may be attenuated or revalidated but never silently expanded.

**Affected files**

- `src/fastapi_mergen/handlers/registry.py`
- `src/fastapi_mergen/handlers/executor.py`
- `src/fastapi_mergen/handlers/dependencies.py`
- `src/fastapi_mergen/api.py`
- `tests/security/test_handler_authority.py`
- `tests/security/test_handler_session_isolation.py`

**Definition of Done**

- [x] Handlers resolve by immutable route key/version rather than mutable function name alone.
- [x] Snapshot authority enforces maximum age and route attenuation.
- [x] Revalidation intersects current scopes with origin ceiling and route allowance and observes revocation.
- [x] Service policy is explicit, pre-resolved, and distinguishable from user authority.
- [x] Every attempt receives a new `mergen_app` session bound to the delivery tenant; relay and request sessions are never injected.
- [x] Handler timeout, dependency cleanup, and principal reset execute on success, error, and cancellation.

### - [x] M8.17 — Add runtime observability primitives

**Estimate:** 5–8 h
**Depends on:** M8.11–M8.16

**Goal**

Expose vendor-neutral metrics, structured events, and trace propagation for the core engine without payload or credential leakage.

**Context**

Operational correctness needs backlog, attempts, lease loss, dead-letter, replay, and latency visibility. Observability must remain optional and secret-minimizing.

**Affected files**

- `src/fastapi_mergen/observability/protocols.py`
- `src/fastapi_mergen/observability/events.py`
- `src/fastapi_mergen/observability/otel.py`
- `tests/security/test_observability_redaction.py`
- `docs/reference/observability.md`

**Definition of Done**

- [x] No-op protocols impose no optional dependency on the base import.
- [x] Core events cover publish, claim, attempt, retry, success, dead, lease loss, reconciliation, and replay.
- [x] Traceparent/tracestate propagate without accepting malformed or oversized values.
- [x] Metrics and logs exclude payload bodies, credentials, secrets, and unbounded exception text.
- [x] The `otel` extra maps stable attributes without changing core behavior.

### - [ ] M8.18 — Certify the real core runtime and release

**Estimate:** 12–18 h
**Depends on:** M8.01–M8.17

**Goal**

Connect the conformance suite to the real PostgreSQL/application paths, complete the invoicing vertical slice, and package `0.7.0a1`.

**Context**

The assurance suite becomes valuable only when it tests the production implementation. This task is the milestone integration and release gate, not a separate reference-driver run.

**Affected files**

- `src/fastapi_mergen/testing/postgres_driver.py`
- `tests/conformance/test_real_core_runtime.py`
- `examples/invoicing/`
- `scripts/audit_milestone_eight.py`
- `README.md`
- `CHANGELOG.md`
- `.github/workflows/ci.yml`

**Definition of Done**

- [x] The real adapter invokes actual UoW, PostgreSQL, relay, handler, RLS, and lease paths.
- [x] `core`, `delivery`, and `security` profiles certify on PostgreSQL 16 and 18.
- [x] The invoicing example completes authenticated request → atomic emit → relay → tenant-bound handler.
- [ ] Unit, integration, security, chaos, Ruff, mypy, lock, build, Twine, clean-install, Git, and extracted-archive gates pass.
- [x] No advertised core path raises `MilestoneNotImplementedError`.
- [x] `0.7.0a1` documentation states its alpha limitations and at-least-once guarantee precisely.

The adapter now crosses PostgreSQL RLS for denial probes and executes finalized claims
through `PollingRelay` and `HandlerExecutor`; it does not pre-reject tenants or directly
invoke lease finalization. Local gates pass; the combined gate remains open because this
working tree has not been committed under the repository Git-governance policy.

---

## M9 — Webhook Minimum Differentiated Product

**Target:** `0.8.0b1`, then `0.8.0` after external validation
**Estimated total:** 75–105 hours
**Milestone exit:** real webhook path certifies the `webhook` profile

### - [x] M9.01 — Add subscription and secret persistence

**Estimate:** 9–13 h
**Depends on:** M8 complete

**Goal**

Introduce tenant-scoped webhook subscriptions, immutable versions, signing-secret sets, lifecycle states, indexes, grants, and RLS.

**Context**

Future subscription changes must affect only future route snapshotting. Already committed deliveries retain their endpoint and policy intent.

**Affected files**

- `src/fastapi_mergen/webhooks/models.py`
- `src/fastapi_mergen/webhooks/subscriptions.py`
- `src/fastapi_mergen/postgres/migrations/versions/0002_webhooks.py`
- `tests/integration/test_webhook_schema.py`

**Definition of Done**

- [x] Subscription identity, version, exact event types, endpoint, status, retry profile, and audit fields are persisted.
- [x] Secret sets and versions use active, retiring, and revoked states.
- [x] Forced RLS and composite tenant-safe relationships protect all webhook tables.
- [x] Update/deactivate operations use optimistic version checks.
- [x] Migration upgrade/downgrade passes PostgreSQL 16/18.

### - [x] M9.02 — Implement encrypted secret lifecycle

**Estimate:** 8–12 h
**Depends on:** M9.01

**Goal**

Provide AES-GCM envelope encryption, master-key provider protocols, one-time plaintext return, rotation overlap, and revocation.

**Context**

PostgreSQL stores ciphertext and key metadata only. Plaintext signing material must remain in bounded process memory and never enter snapshots, errors, logs, or conformance evidence.

**Affected files**

- `src/fastapi_mergen/webhooks/secrets.py`
- `src/fastapi_mergen/webhooks/models.py`
- `tests/security/test_webhook_secrets.py`
- `docs/operations/webhook-secrets.md`

**Definition of Done**

- [x] Encryption uses a reviewed cryptography implementation with tenant/secret identity as associated data.
- [x] Master keys come from an application provider, not the database.
- [x] Creation and rotation return plaintext only once and expose no recovery API.
- [x] Retiring overlap and immediate revocation are deterministic and bounded.
- [x] Secret material is absent from repr, exceptions, metrics, logs, rows outside the ciphertext table, and public evidence.

### - [x] M9.03 — Snapshot subscriptions into deliveries

**Estimate:** 7–10 h
**Depends on:** M9.01–M9.02

**Goal**

Resolve eligible exact-event subscriptions during `emit()` and create immutable webhook delivery specifications in the originating transaction.

**Context**

Delivery routing must not query mutable subscription state during retry. Pausing a subscription affects future events but does not silently cancel committed work.

**Affected files**

- `src/fastapi_mergen/webhooks/subscriptions.py`
- `src/fastapi_mergen/sqlalchemy/uow.py`
- `src/fastapi_mergen/core/routing.py`
- `tests/integration/test_webhook_snapshotting.py`

**Definition of Done**

- [x] Exact event matching creates one delivery per active eligible subscription.
- [x] Destination snapshots contain subscription/version, endpoint URL, secret-set reference, and retry policy without plaintext secrets.
- [x] Later URL, status, key, or policy changes do not mutate existing deliveries.
- [x] Paused/disabled subscriptions are excluded from future snapshotting according to documented semantics.
- [x] An error while snapshotting any destination rolls back the business transaction and all intent rows.

### - [x] M9.04 — Implement deterministic webhook envelopes and signing

**Estimate:** 7–10 h
**Depends on:** M9.02–M9.03

**Goal**

Serialize one deterministic wire envelope per delivery and generate Standard Webhooks-compatible headers from active and eligible retiring keys.

**Context**

The exact bytes signed must be the exact bytes sent. Automatic retry preserves body and message ID; explicit replay creates a new delivery/message identity.

**Affected files**

- `src/fastapi_mergen/webhooks/serializer.py`
- `src/fastapi_mergen/webhooks/signing.py`
- `tests/unit/test_webhook_envelope.py`
- `tests/unit/test_webhook_signing.py`

**Definition of Done**

- [x] Envelope includes stable delivery message ID, event identity/type/version, tenant, occurrence time, and typed data.
- [x] Canonical body bytes remain stable across automatic retries.
- [x] Headers contain valid ID, timestamp, and one or more v1 signatures.
- [x] Rotation overlap produces multiple verifiable signatures without changing message identity.
- [x] Standard Webhooks vectors and the reference receiver verify successfully.

### - [x] M9.05 — Implement hostile endpoint validation

**Estimate:** 8–12 h
**Depends on:** M9.01

**Goal**

Parse and classify webhook endpoints and DNS answers fail-closed before every connection attempt.

**Context**

Registration-time URL validation is insufficient. DNS and address policy must be applied at attempt time and reject mixed public/forbidden answers.

**Affected files**

- `src/fastapi_mergen/webhooks/transport.py`
- `src/fastapi_mergen/webhooks/address_policy.py`
- `tests/security/test_webhook_ssrf.py`
- `tests/security/fixtures/dns.py`

**Definition of Done**

- [x] Production mode requires HTTPS and rejects userinfo, fragments, malformed authorities, control characters, and disallowed ports.
- [x] Hostnames are IDNA-normalized and resolved on every attempt.
- [x] Private, loopback, link-local, metadata, carrier-grade NAT, multicast, reserved, documentation, benchmark, and unspecified addresses are blocked.
- [x] IPv4-mapped IPv6 and mixed DNS answer sets are handled fail-closed.
- [x] DNS rebinding fixtures cannot trigger an unvalidated second resolution.

### - [x] M9.06 — Implement explicit-IP TLS transport

**Estimate:** 10–14 h
**Depends on:** M9.04–M9.05

**Goal**

Connect to a previously validated explicit IP while preserving the original hostname for TLS verification, SNI, and HTTP authority.

**Context**

A generic HTTP client that resolves the hostname again can invalidate the SSRF check. The transport must own the connection boundary and retain strict hostname validation.

**Affected files**

- `src/fastapi_mergen/webhooks/transport.py`
- `src/fastapi_mergen/webhooks/http11.py`
- `tests/security/test_explicit_ip_tls.py`
- `tests/security/fixtures/tls.py`

**Definition of Done**

- [x] The connection target is exactly one validated IP from the approved answer set.
- [x] TLS certificate and SNI use the original normalized hostname.
- [x] HTTP Host/authority remains the original hostname and validated port.
- [x] Redirects are disabled by default; enabled redirects repeat full URL/DNS/IP validation.
- [x] TLS 1.2+ and hostname verification are mandatory in production mode.

### - [x] M9.07 — Bound HTTP delivery and classify failures

**Estimate:** 8–12 h
**Depends on:** M9.04–M9.06

**Goal**

Enforce total/connect/write/read limits, byte limits, concurrency controls, complete HTTP parsing, and deterministic retry classification.

**Context**

Hostile receivers can stall, stream indefinitely, return oversized headers/bodies, or manipulate retry timing. The relay must persist only bounded metadata.

**Affected files**

- `src/fastapi_mergen/webhooks/http11.py`
- `src/fastapi_mergen/webhooks/sink.py`
- `src/fastapi_mergen/webhooks/transport.py`
- `tests/security/test_webhook_response_bounds.py`
- `tests/unit/test_retry_after.py`

**Definition of Done**

- [x] Request, response, header, redirect, and total-duration limits are configurable and enforced.
- [x] Chunked responses consume terminal chunks and trailers correctly while discarding body content.
- [x] 2xx succeeds; 408/425/429/5xx and transient transport failures retry; deterministic policy failures terminate.
- [x] `Retry-After` parses supported forms and is clamped by route policy and delivery deadline.
- [x] No receiver response body is persisted or included in ordinary exceptions/evidence.

### - [x] M9.08 — Add webhook operations and lifecycle

**Estimate:** 9–13 h
**Depends on:** M9.01–M9.07

**Goal**

Expose tenant-safe subscription CRUD, delivery/attempt inspection, replay, dead-letter, pause/reactivate, secret rotation, and retention operations.

**Context**

Operational actions change security or delivery intent and therefore need explicit authorization, audit records, immutable history, and bounded database work.

**Affected files**

- `src/fastapi_mergen/webhooks/api.py`
- `src/fastapi_mergen/webhooks/operations.py`
- `src/fastapi_mergen/cli/webhooks.py`
- `tests/integration/test_webhook_operations.py`
- `docs/operations/webhooks.md`

**Definition of Done**

- [x] All operations require tenant-bound application authority or an explicit restricted operator role.
- [x] Manual replay creates a new linked delivery and never mutates the original terminal row.
- [x] Pause/reactivate affects future snapshotting and records an audit event.
- [x] Secret rotation and revocation follow lifecycle rules and optimistic concurrency.
- [x] Retention deletes attempts, deliveries, unreferenced events, and retired secret material in bounded dependency-safe batches.

### - [x] M9.09 — Add webhook observability and auto-pause

**Estimate:** 5–8 h
**Depends on:** M9.07–M9.08

**Goal**

Track endpoint health, failure streaks, auto-pause decisions, delivery latency, retries, dead letters, and key operations without exposing payload or secret data.

**Context**

Persistent endpoint failure can create unbounded backlog and operational noise. Auto-pause must be explicit, auditable, and limited to future snapshotting.

**Affected files**

- `src/fastapi_mergen/webhooks/operations.py`
- `src/fastapi_mergen/observability/events.py`
- `tests/integration/test_webhook_auto_pause.py`
- `tests/security/test_webhook_metrics_redaction.py`

**Definition of Done**

- [x] Success resets failure streaks and qualifying terminal/retryable outcomes increment them according to policy.
- [x] Threshold crossing pauses the subscription for future events and emits one audit/metric event.
- [x] Existing committed deliveries are not silently cancelled.
- [x] Metrics include status class, latency, retry, dead, pause, and backlog counts without URL credentials, payloads, or secret IDs beyond approved opaque identifiers.

### - [x] M9.10 — Certify webhook failure and crash boundaries

**Estimate:** 8–12 h
**Depends on:** M9.01–M9.09

**Goal**

Connect the real webhook sink to the conformance suite and execute hostile-network and ambiguous-crash scenarios.

**Context**

The release needs evidence from the actual DNS/TLS/HTTP/store path, not only deterministic unit fixtures or the in-memory reference driver.

**Affected files**

- `src/fastapi_mergen/testing/webhook_driver.py`
- `tests/conformance/test_real_webhooks.py`
- `tests/chaos/test_webhook_crash_matrix.py`
- `scripts/audit_milestone_nine.py`

**Definition of Done**

- [x] The real adapter passes the `webhook` profile against PostgreSQL 16 and 18.
- [x] Receiver-success/relay-crash produces a retry with the same message ID and a receiver dedupe example yields one effective outcome.
- [x] All documented SSRF and response-boundary cases fail closed.
- [x] Rotation overlap, replay identity, pause behavior, and secret minimization are covered by integration tests.
- [x] Evidence contains no configured secret canary or receiver-controlled body content.

The conformance adapter provisions an encrypted signing secret and subscription, emits a
real delivery, validates the supplied public DNS answer, and sends through the production
explicit-IP TLS/HTTP parser to a deterministic local TLS receiver. Receiver-controlled
response bodies are consumed and discarded. Redirects remain disabled by default; an
enabled bounded redirect repeats endpoint parsing, DNS resolution, and public-IP validation.

### - [ ] M9.11 — Ship the webhook MDP beta

**Estimate:** 8–12 h
**Depends on:** M9.01–M9.10

**Goal**

Complete the receiver, production-style deployment, documentation, design-partner handoff, and `0.8.0b1` package.

**Context**

The webhook MDP is the first marketable product. Its release gate includes adoption and operations, not only code completion.

**Affected files**

- `examples/webhook_receiver/`
- `examples/invoicing/`
- `docs/tutorials/webhook-vertical-slice.md`
- `README.md`
- `CHANGELOG.md`
- `.github/workflows/release.yml`

**Definition of Done**

- [x] A deduplicating receiver verifies signatures, records stable IDs, and demonstrates duplicate suppression.
- [x] The invoicing deployment covers create → atomic snapshot → failed delivery → retry → success → replay.
- [x] Runbooks cover keys, pause, replay, dead letters, retention, DNS/TLS failures, and ambiguous crashes.
- [ ] Every mandatory build, security, PostgreSQL, conformance, clean-install, Git, and extracted-archive gate passes.
- [ ] One design partner receives a reproducible staging guide and records structured feedback before promotion from beta to `0.8.0`.

The local artifact/runtime gates pass. Git-governance and the external design-partner
gate require maintainer action and independent deployment evidence.

---

## M10 — Taskiq external-executor adapter

**Target:** `0.9.0a1`
**Estimated total:** 40–60 hours
**Milestone exit:** real Taskiq path certifies the `executor` profile

### - [x] M10.01 — Freeze the executor handoff contract

**Estimate:** 4–6 h
**Depends on:** M8 complete

**Goal**

Define the durable handoff state machine, Taskiq responsibility boundary, stable identities, retry ownership, and crash outcomes before adapter coding.

**Context**

Broker acceptance is not handler completion. Mergen must remain the authority for delivery attempts, terminal state, and retry policy.

**Affected files**

- `docs/adr/ADR-011-taskiq-handoff.md`
- `src/fastapi_mergen/executors/protocols.py`
- `docs/reference/executor-boundary.md`

**Definition of Done**

- [x] Prepared, enqueued, executing, succeeded, retry-wait, and dead semantics are documented.
- [x] Per-attempt handoff, stable Taskiq task ID, execution token, and expiry identity are fixed.
- [x] The adapter envelope excludes sessions, database credentials, raw auth tokens, and secrets.
- [x] Taskiq retry middleware is explicitly excluded from application-level retry authority.

### - [x] M10.02 — Add durable Taskiq handoff storage

**Estimate:** 7–10 h
**Depends on:** M10.01

**Goal**

Create the handoff table, constraints, RLS, indexes, migration, and SQLAlchemy repository.

**Context**

A handoff belongs to a specific Mergen delivery attempt. Historical handoffs must remain immutable while execution state is fenced by tokens.

**Affected files**

- `src/fastapi_mergen/executors/taskiq/models.py`
- `src/fastapi_mergen/executors/taskiq/store.py`
- `src/fastapi_mergen/postgres/migrations/versions/0003_taskiq.py`
- `tests/integration/test_taskiq_handoff_schema.py`

**Definition of Done**

- [x] Handoff identity includes tenant, delivery, attempt, stable task ID, immutable token, principal snapshot/reference, route, and event metadata.
- [x] State constraints require coherent execution token/deadline and terminal fields.
- [x] Application reads are tenant-restricted; control-plane mutations are narrowly granted.
- [x] Migration upgrade/downgrade passes PostgreSQL 16/18.

### - [x] M10.03 — Implement Taskiq enqueue bridging

**Estimate:** 6–9 h
**Depends on:** M10.01–M10.02

**Goal**

Register one bridge task and enqueue a bounded immutable handoff envelope with a deterministic Taskiq task ID.

**Context**

The adapter should use Taskiq's supported registration/kicker API and remain lazy behind the optional extra. A successful enqueue is recorded as nonterminal.

**Affected files**

- `src/fastapi_mergen/executors/taskiq/adapter.py`
- `src/fastapi_mergen/executors/taskiq/envelope.py`
- `pyproject.toml`
- `tests/unit/test_taskiq_enqueue.py`

**Definition of Done**

- [x] Base package and adapter module import without eagerly importing Taskiq.
- [x] `pip install 'fastapi-mergen[taskiq]'` installs the supported Taskiq range.
- [x] Task IDs are stable for one delivery attempt and safe for logs/metrics.
- [x] Broker acceptance moves only to `enqueued`; it never marks the delivery or handoff succeeded.
- [x] Enqueue failure maps to Mergen retry/dead-letter policy without losing the handoff record.

### - [x] M10.04 — Implement worker claims and principal restoration

**Estimate:** 7–10 h
**Depends on:** M10.02–M10.03

**Goal**

Claim handoffs atomically in the Taskiq worker, restore the frozen principal, and execute through a fresh tenant-bound application session.

**Context**

Duplicate broker messages are expected. Only one worker may become the active executor for a handoff, and no process context may leak between jobs.

**Affected files**

- `src/fastapi_mergen/executors/taskiq/worker.py`
- `src/fastapi_mergen/executors/taskiq/store.py`
- `tests/security/test_taskiq_context.py`
- `tests/integration/test_taskiq_worker_claim.py`

**Definition of Done**

- [x] Prepared/enqueued → executing uses a unique execution token and bounded deadline.
- [x] A concurrent duplicate receives a bounded no-op result and does not execute the handler.
- [x] Principal binding and fresh `mergen_app` session occur before application SQL.
- [x] Relay, broker, and request sessions are never passed to application code.
- [x] Principal, dependency, and session cleanup runs unconditionally.

### - [x] M10.05 — Implement fenced finalization and recovery

**Estimate:** 7–10 h
**Depends on:** M10.04

**Goal**

Finalize Taskiq execution through execution-token compare-and-set and reconcile expired prepared, enqueued, or executing handoffs.

**Context**

A stale worker must not overwrite a newer retry or completion. Ambiguous crashes may duplicate external effects, so stable application dedupe identity must remain available.

**Affected files**

- `src/fastapi_mergen/executors/taskiq/store.py`
- `src/fastapi_mergen/executors/taskiq/recovery.py`
- `tests/chaos/test_taskiq_crashes.py`
- `tests/integration/test_taskiq_finalization.py`

**Definition of Done**

- [x] Success, retryable failure, and terminal failure require the active execution token.
- [x] Finalization clears execution-only fields and updates the parent Mergen attempt consistently.
- [x] Expired work returns to retry-wait or dead according to Mergen attempt budget.
- [x] A stale worker cannot finalize after expiry/reclaim.
- [x] Crash tests document and preserve stable event/delivery identity for handler-side deduplication.

### - [x] M10.06 — Certify the real Taskiq adapter

**Estimate:** 5–8 h
**Depends on:** M10.01–M10.05

**Goal**

Run the executor profile through a real Taskiq broker/worker path and inject duplicate, failure, expiry, and context-leak cases.

**Context**

Unit mocks cannot certify broker serialization, task registration, duplicate delivery, or worker process lifecycle.

**Affected files**

- `src/fastapi_mergen/testing/taskiq_driver.py`
- `tests/conformance/test_real_taskiq.py`
- `tests/integration/taskiq/`
- `scripts/audit_milestone_ten.py`

**Definition of Done**

- [x] The real adapter passes the `executor` profile.
- [x] Broker acceptance is observed as nonterminal and worker completion as terminal.
- [x] Duplicate messages produce one active execution.
- [x] Sequential tenants show no context/session leakage.
- [x] Worker crash and expiry cases produce bounded retry/dead outcomes without stale finalization.

Executor certification uses Redis Streams and a separately launched Taskiq CLI worker.
The producer observes the durable `enqueued` state before starting the worker, while the
worker receives Taskiq's serialized broker message and PostgreSQL fences duplicate delivery.

### - [ ] M10.07 — Document and package the Taskiq alpha

**Estimate:** 4–7 h
**Depends on:** M10.01–M10.06

**Goal**

Publish a minimal integration guide, worker deployment example, compatibility matrix, and `0.9.0a1` artifacts.

**Context**

The integration must not imply that Mergen replaces Taskiq or makes external effects exactly once.

**Affected files**

- `docs/integrations/taskiq.md`
- `examples/taskiq_worker/`
- `README.md`
- `CHANGELOG.md`
- `.github/workflows/ci.yml`

**Definition of Done**

- [x] Documentation states the two-system responsibility boundary and retry authority.
- [x] Example includes broker startup, bridge registration, tenant session factory, and graceful shutdown.
- [x] Taskiq extra isolation and clean-wheel tests pass.
- [ ] All mandatory release and extracted-archive gates pass for `0.9.0a1`.

Clean artifacts pass; the release/Git-governance portion remains a maintainer gate.

---

## M11 — Transactional inbound command idempotency

**Target:** `0.10.0a1`
**Estimated total:** 45–65 hours
**Milestone exit:** live concurrent requests prove one committed command outcome

### - [x] M11.01 — Freeze command identity and fingerprint semantics

**Estimate:** 5–7 h
**Depends on:** M8 complete

**Goal**

Define the exact command namespace, subject binding, fingerprint format, replay policy, expiry generations, and unsupported response forms.

**Context**

A middleware cache cannot make application database writes atomic. Command idempotency must own the same outer transaction as the protected business operation.

**Affected files**

- `docs/adr/ADR-012-command-idempotency.md`
- `src/fastapi_mergen/idempotency/models.py`
- `docs/reference/command-idempotency.md`

**Definition of Done**

- [x] Identity is tenant + stable route + method + SHA-256 opaque-key digest.
- [x] Subject binding and mismatch behavior are explicit.
- [x] Fingerprint version covers path parameters, exact query representation, selected headers, media type, and body identity.
- [x] Replayable response types and security exclusions are fixed.
- [x] Raw idempotency keys are never stored or logged.

### - [x] M11.02 — Add the command ledger migration

**Estimate:** 8–11 h
**Depends on:** M11.01

**Goal**

Create immutable command generations, response fields, RLS policies, indexes, grants, and mutation-prevention trigger.

**Context**

Expired identities create new generations while completed historical generations remain immutable until retention removes them.

**Affected files**

- `src/fastapi_mergen/idempotency/models.py`
- `src/fastapi_mergen/postgres/migrations/versions/0004_commands.py`
- `tests/integration/test_command_schema.py`

**Definition of Done**

- [x] One partial unique index permits exactly one current generation per command identity.
- [x] Digest, fingerprint, state, response, timestamp, generation, and supersession constraints reject impossible rows.
- [x] Trigger prevents identity/fingerprint/completed-response mutation and illegal transitions.
- [x] Application RLS and restricted maintenance grants are tested live.
- [x] Upgrade/downgrade passes PostgreSQL 16/18.

### - [x] M11.03 — Implement request fingerprinting

**Estimate:** 7–10 h
**Depends on:** M11.01

**Goal**

Parse bounded request bodies and produce strict, deterministic fingerprints that fail closed on ambiguous JSON or malformed input.

**Context**

Semantically different commands must not share an idempotency identity. JSON object order may normalize, while query order may remain significant to the application.

**Affected files**

- `src/fastapi_mergen/idempotency/fingerprint.py`
- `src/fastapi_mergen/idempotency/request.py`
- `tests/security/test_command_fingerprints.py`

**Definition of Done**

- [x] Opaque keys preserve exact caller bytes before hashing and enforce length/control-character bounds.
- [x] JSON rejects duplicate keys, malformed UTF-8, non-finite values, and oversized bodies.
- [x] Raw-body and canonical-JSON modes are explicit and versioned.
- [x] Selected representation/precondition headers are normalized according to documented rules.
- [x] Fingerprint vectors are stable across supported Python versions.

### - [x] M11.04 — Implement advisory-lock command storage

**Estimate:** 7–10 h
**Depends on:** M11.02–M11.03

**Goal**

Serialize the no-row race through a transaction-scoped advisory lock and resolve new, replay, conflict, expired, and in-progress command states.

**Context**

A row lock cannot protect an identity before the first row exists. The lock must derive from the complete command identity and remain bounded by command transaction policy.

**Affected files**

- `src/fastapi_mergen/idempotency/store.py`
- `tests/integration/test_command_concurrency.py`
- `tests/chaos/test_command_rollback_window.py`

**Definition of Done**

- [x] The first transaction claims the identity before business writes.
- [x] A concurrent identical request waits and then replays the committed response.
- [x] Rollback removes claim and business writes, allowing a later request to execute.
- [x] Fingerprint or subject mismatch returns a bounded conflict without revealing stored details.
- [x] Expired current generations are superseded safely and history remains immutable.

### - [x] M11.05 — Implement transactional command context

**Estimate:** 7–10 h
**Depends on:** M11.04

**Goal**

Provide an explicit async context that owns the outer transaction and requires a replayable response before successful exit.

**Context**

Endpoint code must use one session and cannot commit independently. Missing completion or unsafe response capture must roll back the protected business operation.

**Affected files**

- `src/fastapi_mergen/idempotency/command.py`
- `src/fastapi_mergen/sqlalchemy/uow.py`
- `tests/unit/test_command_context.py`
- `tests/integration/test_command_atomicity.py`

**Definition of Done**

- [x] Entry rejects an already active transaction and binds tenant/subject context before SQL.
- [x] Replay state bypasses business execution and returns the stored response.
- [x] New state requires `complete()` before normal exit.
- [x] Application exception, missing completion, or publication failure rolls back claim and business writes.
- [x] Context and session cleanup are unconditional.

### - [x] M11.06 — Implement safe response capture and replay

**Estimate:** 6–9 h
**Depends on:** M11.01, M11.05

**Goal**

Capture only bounded replay-safe responses and reconstruct them without persisting transport, authentication, cookie, or streaming state.

**Context**

The replay record is durable application data. Unsafe headers or bodies can leak credentials, create stale sessions, or make response semantics misleading.

**Affected files**

- `src/fastapi_mergen/idempotency/responses.py`
- `tests/security/test_response_capture.py`
- `tests/unit/test_response_replay.py`

**Definition of Done**

- [x] Default allowed media types and maximum body/header sizes are explicit.
- [x] Streaming, `Set-Cookie`, authorization/authentication, hop-by-hop, malformed, and newline-bearing headers are rejected or excluded as documented.
- [x] Status, safe headers, content type, and body replay exactly within the declared policy.
- [x] Replayed responses add a safe `Idempotency-Replayed` indicator.
- [x] Stored records and exceptions reveal no raw key or unsafe header value.

### - [x] M11.07 — Add FastAPI integration and operations

**Estimate:** 6–9 h
**Depends on:** M11.03–M11.06

**Goal**

Expose request preparation, command dependency/context helpers, bounded exception mapping, replay, expiry, and pruning operations.

**Context**

The integration should remain explicit enough that transaction ownership and response completion are visible in endpoint code.

**Affected files**

- `src/fastapi_mergen/idempotency/api.py`
- `src/fastapi_mergen/idempotency/cli.py`
- `src/fastapi_mergen/cli/main.py`
- `tests/integration/test_idempotent_endpoint.py`
- `docs/operations/command-idempotency.md`

**Definition of Done**

- [x] Request body collection is bounded and leaves the body available to endpoint parsing.
- [x] Endpoint example uses the command-owned session for all protected writes.
- [x] 401/403/409/413/422/500 mappings are bounded and do not disclose stored fingerprints or keys.
- [x] Pruning operates in bounded `SKIP LOCKED` batches under restricted maintenance authority.
- [x] Runbook covers expiry, conflicts, retention, rollback, and external-effect limitations.

### - [ ] M11.08 — Certify and release command idempotency

**Estimate:** 6–9 h
**Depends on:** M11.01–M11.07

**Goal**

Run live concurrent FastAPI/PostgreSQL scenarios, connect the command facet to conformance, and package `0.10.0a1`.

**Context**

The key proof is one committed application transaction under real concurrency, not a mocked cache hit.

**Affected files**

- `src/fastapi_mergen/testing/idempotency_driver.py`
- `tests/conformance/test_real_commands.py`
- `tests/chaos/test_command_crashes.py`
- `scripts/audit_milestone_eleven.py`
- `CHANGELOG.md`

**Definition of Done**

- [x] Concurrent identical requests commit one business result and replay one response.
- [x] Conflict, rollback, expiry, subject mismatch, unsafe response, and pruning cases pass PostgreSQL 16/18.
- [x] Real conformance scenarios detect duplicate-command and fingerprint-reuse defects.
- [ ] All mandatory quality, packaging, Git, and extracted-archive gates pass for `0.10.0a1`.

All local quality, packaging, and archive gates pass; Git governance remains open.

---

## M12 — Delegation and FastMCP integration

**Target:** `0.11.0a1`
**Estimated total:** 45–65 hours
**Milestone exit:** exact audience/method/path and non-expanding scopes are verified end to end

### - [x] M12.01 — Freeze the delegation threat model

**Estimate:** 5–7 h
**Depends on:** M8 complete; concrete user requirement

**Goal**

Define issuer/verifier trust, caller-metadata provenance, token lifetime, audience/target binding, scope attenuation, delegation depth, rotation, revocation, and audit semantics.

**Context**

FastMCP tool visibility is not authorization, and transport credentials must not be blindly forwarded. The bridge needs a new, short-lived next-hop authority representation.

**Affected files**

- `docs/adr/ADR-013-delegation.md`
- `docs/concepts/delegation-threat-model.md`
- `src/fastapi_mergen/delegation/protocols.py`

**Definition of Done**

- [x] Trusted caller metadata and untrusted transport inputs are clearly separated.
- [x] The credential contains no original bearer token and has an exact downstream audience.
- [x] Method/path binding and canonicalization rules are fixed.
- [x] Scope and delegation-depth non-expansion rules are normative.
- [x] Tool discovery remains explicitly separate from downstream route authorization.

### - [x] M12.02 — Implement delegation claims and encoding

**Estimate:** 6–9 h
**Depends on:** M12.01

**Goal**

Create a bounded versioned credential model with issuer, tenant, subject, actor, client, audience, target, scopes, times, token ID, key ID, and delegation depth.

**Context**

The credential is an internal delegation artifact, not a serialized request or copied OAuth token. All fields require strict syntax and size validation.

**Affected files**

- `src/fastapi_mergen/delegation/models.py`
- `src/fastapi_mergen/delegation/encoding.py`
- `tests/unit/test_delegation_claims.py`

**Definition of Done**

- [x] Claim validation rejects missing identity, invalid times, excess lifetime, oversized scopes, and unsupported versions.
- [x] Canonical encoding is deterministic and separates signed bytes from transport wrapper.
- [x] Token IDs and key IDs are opaque, bounded, and safe for audit metadata.
- [x] No raw caller credential, cookie, or arbitrary header can enter the claims model.

### - [x] M12.03 — Implement signing key lifecycle

**Estimate:** 6–9 h
**Depends on:** M12.01–M12.02

**Goal**

Provide signing/verifying key-ring protocols, active/retiring/revoked states, bounded overlap, and immediate revocation.

**Context**

Verification must identify one key by `kid` rather than trying every key, and rotation must not silently extend token validity.

**Affected files**

- `src/fastapi_mergen/delegation/keys.py`
- `src/fastapi_mergen/delegation/signing.py`
- `tests/security/test_delegation_keys.py`
- `docs/operations/delegation-keys.md`

**Definition of Done**

- [x] Only active keys sign new credentials unless policy explicitly permits otherwise.
- [x] Retiring keys verify only during their bounded overlap and original credential lifetime.
- [x] Revoked keys fail immediately.
- [x] Key material is absent from tokens beyond `kid`, and absent from logs/evidence.
- [x] Rotation and revocation are auditable without token capture.

### - [x] M12.04 — Implement target-bound verification

**Estimate:** 8–11 h
**Depends on:** M12.02–M12.03

**Goal**

Verify signature, issuer, audience, time, tenant, scopes, delegation depth, HTTP method, and exact canonical target path fail-closed.

**Context**

Path normalization ambiguity can turn a narrowly delegated credential into broader authority. Verification must compare the same canonical target that issuance signed.

**Affected files**

- `src/fastapi_mergen/delegation/verification.py`
- `src/fastapi_mergen/delegation/targets.py`
- `tests/security/test_delegation_targets.py`

**Definition of Done**

- [x] Traversal, encoded traversal, backslash variants, malformed percent encoding, control characters, scheme-relative, authority-bearing, query, and fragment confusion fail closed.
- [x] Audience and issuer comparison are exact and bounded.
- [x] Required scopes are a subset of delegated scopes, which are a subset of verified parent/route authority.
- [x] Expired, future, overlong, excessive-depth, revoked-key, and unsupported-version credentials fail with bounded errors.
- [x] Verifier never logs raw credentials or signatures.

### - [x] M12.05 — Implement the FastMCP delegation bridge

**Estimate:** 7–10 h
**Depends on:** M12.01–M12.04

**Goal**

Issue a target-bound internal credential from trusted authenticated caller metadata and attach it to downstream FastAPI calls without forwarding inbound credentials.

**Context**

The bridge is an integration with FastMCP, not an MCP implementation. It must strip credential-bearing inbound headers and use only trusted caller identity supplied by the host authentication layer.

**Affected files**

- `src/fastapi_mergen/integrations/fastmcp.py`
- `src/fastapi_mergen/delegation/bridge.py`
- `pyproject.toml`
- `tests/security/test_fastmcp_bridge.py`

**Definition of Done**

- [x] Base package imports without FastMCP and the optional extra installs the certified version range.
- [x] Inbound authorization, proxy-authorization, cookie, and session credentials are never forwarded.
- [x] Component policy attenuates requested scopes before issuance.
- [x] The issued credential binds exact audience, method, and canonical path.
- [x] Discovery filtering does not suppress downstream authorization enforcement.

### - [x] M12.06 — Add downstream FastAPI enforcement and audit

**Estimate:** 5–8 h
**Depends on:** M12.04–M12.05

**Goal**

Provide a FastAPI dependency that verifies delegation, reconstructs a principal, enforces route scopes, and emits token-free audit events.

**Context**

The downstream API is the final authorization boundary. Audit must retain identity and decision provenance without storing the delegation credential or signature.

**Affected files**

- `src/fastapi_mergen/delegation/fastapi.py`
- `src/fastapi_mergen/delegation/audit.py`
- `tests/integration/test_delegated_route.py`
- `tests/security/test_delegation_audit.py`

**Definition of Done**

- [x] Verified claims reconstruct tenant, subject, actor, client, scopes, and delegation provenance.
- [x] Route-required scopes are enforced independently of MCP discovery state.
- [x] Audit includes approved IDs, audience, target identifier, scopes, key ID, outcome, and trace lineage only.
- [x] Tokens, signatures, cookies, raw headers, and signing keys are absent from persistence and evidence.
- [x] Failure responses are bounded 401/403 outcomes without verifier internals.

### - [x] M12.07 — Certify delegation security boundaries

**Estimate:** 5–8 h
**Depends on:** M12.01–M12.06

**Goal**

Connect the real bridge and verifier to conformance and run scope-expansion, target-confusion, replay, rotation, revocation, and credential-leak tests.

**Context**

A unit-signed token alone does not prove the actual FastMCP-to-ASGI/downstream path or the stripping of inbound credentials.

**Affected files**

- `src/fastapi_mergen/testing/delegation_driver.py`
- `tests/conformance/test_real_delegation.py`
- `tests/security/test_delegation_end_to_end.py`
- `scripts/audit_milestone_twelve.py`

**Definition of Done**

- [x] The real delegation facet detects authority expansion and loose target binding defects.
- [x] End-to-end tests prove no inbound bearer/cookie credential reaches the downstream request.
- [x] Audience/method/path mismatch, revoked key, expiry, excessive depth, and missing scopes fail closed.
- [x] Evidence secret-canary scans pass.
- [x] The test matrix uses the certified FastMCP integration version.

### - [x] M12.08 — Document and package delegation alpha

**Estimate:** 4–7 h
**Depends on:** M12.01–M12.07

**Goal**

Publish the host-authentication contract, integration examples, key operations, limitations, and `0.11.0a1` artifacts.

**Context**

Users must understand that Mergen does not authenticate MCP callers and does not make tool visibility an authorization boundary.

**Affected files**

- `docs/integrations/fastmcp.md`
- `examples/fastmcp_delegation/`
- `README.md`
- `CHANGELOG.md`
- `.github/workflows/ci.yml`

**Definition of Done**

- [x] Example includes trusted caller metadata, scope attenuation, bridge dispatch, and downstream verification.
- [x] Documentation explicitly prohibits blind header/token forwarding.
- [x] Key rotation, revocation, audience changes, and incident response are documented.
- [x] Optional-extra isolation, security, conformance, packaging, and extracted-archive gates pass for `0.11.0a1`.

---

## M13 — Production hardening and v1.0

**Target:** `1.0.0rc1` → `1.0.0`
**Estimated engineering total:** 90–130 hours plus external observation
**Milestone exit:** stable migration/API contract and two external production deployments

**Status (2026-08-30):** local engineering and executable evidence are implemented.
Unchecked items below are intentionally fail-closed gates that require protected hosted
checks, independent review, maintainer-controlled Git/release actions, or evidence from
external deployments. The package remains `0.11.0a1`; it has not been mislabeled as an
RC or v1 release.

### - [x] M13.01 — Inventory and freeze the v1 public API

**Estimate:** 7–10 h
**Depends on:** Selected M8–M12 capabilities complete

**Goal**

Review every root export, documented module, protocol, exception, CLI command, environment variable, evidence schema, and migration contract before declaring compatibility.

**Context**

Pre-1.0 history permits changes, but v1 requires a narrow, intentional surface and a documented deprecation process.

**Affected files**

- `src/fastapi_mergen/api.py`
- `src/fastapi_mergen/__init__.py`
- `docs/reference/public-api.md`
- `docs/compatibility.md`
- `CHANGELOG.md`

**Definition of Done**

- [x] Every supported symbol is documented, typed, import-tested, and assigned a compatibility status.
- [x] Internal modules are clearly marked non-contractual.
- [x] Exception safety and stable error codes are reviewed.
- [x] CLI and environment-variable compatibility is documented.
- [x] A deprecation policy and minimum warning period are accepted.

### - [x] M13.02 — Stabilize schema revision history

**Estimate:** 10–14 h
**Depends on:** M13.01

**Goal**

Create a complete revision registry and executable upgrade/downgrade matrix from every published schema-bearing release.

**Context**

Package version and database schema version are related but distinct. Operators need safe, explicit, reversible transitions and actionable startup diagnostics.

**Affected files**

- `src/fastapi_mergen/postgres/migrations/`
- `src/fastapi_mergen/postgres/schema.py`
- `tests/migrations/`
- `docs/operations/migrations.md`

**Definition of Done**

- [x] Every released schema revision upgrades to the candidate head on PostgreSQL 16/18.
- [x] Every supported downgrade path is explicit; irreversible transitions are rejected with documented procedure.
- [x] Data-preservation checks cover events, deliveries, attempts, subscriptions, commands, and handoffs.
- [x] Startup rejects incompatible newer/older schema with actionable detail and no auto-migration.
- [x] Migration ownership, grants, RLS, functions, indexes, and triggers remain correct after every path.

### - [x] M13.03 — Complete the compatibility matrix

**Estimate:** 8–12 h
**Depends on:** M13.01–M13.02

**Goal**

Execute supported Python, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, DBAPI, Taskiq, FastMCP, and optional-extra combinations using minimum/latest jobs.

**Context**

The compatibility table must report executed evidence rather than intended support. A full Cartesian matrix is unnecessary, but risk-based pairwise coverage is mandatory.

**Affected files**

- `.github/workflows/compatibility.yml`
- `tests/compatibility/`
- `docs/compatibility.md`
- `pyproject.toml`

**Definition of Done**

- [x] Python 3.11–3.14 unit and packaging jobs pass.
- [x] PostgreSQL 16/18 pairwise integration jobs pass.
- [x] Minimum and latest dependency jobs pass for base and each advertised extra.
- [x] `asyncpg` is certified; async psycopg is either certified or explicitly deferred with rationale.
- [x] The published matrix links to or embeds machine-readable evidence identifiers.

The pairwise/minimum/latest jobs are implemented in `compatibility.yml`. Every hosted job
writes an execution-bound artifact containing package version, commit, lock digest, Python,
installed distributions, workflow identity, and database/driver versions when applicable.
`docs/evidence/compatibility-local.json` is retained only as a commit/lock-bound historical
snapshot and is explicitly not release-authoritative.

### - [x] M13.04 — Benchmark runtime and database behavior

**Estimate:** 8–12 h
**Depends on:** M13.02–M13.03

**Goal**

Measure emission overhead, claim throughput, fairness, backlog age, retry scheduling, webhook transport, command contention, and retention behavior under documented workloads.

**Context**

Production limits should be empirical and reproducible. Benchmarks are not marketing claims until hardware, schema, dataset, and methodology are published.

**Affected files**

- `benchmarks/`
- `scripts/benchmark.py`
- `docs/operations/performance.md`
- `.github/workflows/benchmarks.yml`

**Definition of Done**

- [x] Benchmark fixtures define hardware/runtime/database versions and dataset shape.
- [x] Results cover single-tenant and multi-tenant contention.
- [x] Claim fairness and starvation bounds are measured under concurrent workers.
- [x] Retention/pruning impact and index growth are measured.
- [x] Regression thresholds are conservative and separate correctness failures from performance alerts.

### - [x] M13.05 — Expand chaos and recovery testing

**Estimate:** 8–12 h
**Depends on:** M13.02–M13.04

**Goal**

Exercise process, database, network, broker, key-provider, and deployment failures across every supported capability.

**Context**

The primary operational promise is no lost committed intent and fenced stale work, not absence of duplicates. Chaos tests must cover ambiguous outcomes honestly.

**Affected files**

- `tests/chaos/`
- `scripts/chaos_harness.py`
- `docs/operations/failure-recovery.md`

**Definition of Done**

- [x] Kill points cover before/after commit, claim, external acceptance, remote success, finalization, replay, and pruning.
- [x] Database restart/failover and connection loss are covered where the supported environment permits.
- [x] Taskiq worker and webhook receiver failures retain stable dedupe identities.
- [x] Key-provider outage and revoked-key cases fail according to documented retry/terminal policy.
- [x] No chaos result is described as exactly-once unless a cooperating deduplicating consumer is part of the scenario.

Real connection termination and persistent-data container restart pass on PostgreSQL 16
and 18 with committed identity, schema, doctor, and pool-recovery checks. Managed-service
failover remains external because the supported local environment is single-node; the
manifest and recovery guide say so explicitly instead of implying promotion coverage.

### - [x] M13.06 — Finish production observability

**Estimate:** 7–10 h
**Depends on:** M13.03–M13.05

**Goal**

Finalize OpenTelemetry traces, stable metrics, structured logs, dashboard examples, and alert guidance for every runtime capability.

**Context**

Operators need to distinguish backlog, receiver failure, authorization denial, lease loss, command conflict, and deployment misconfiguration without inspecting payloads.

**Affected files**

- `src/fastapi_mergen/observability/`
- `docs/operations/observability.md`
- `examples/observability/`
- `tests/security/test_observability_contract.py`

**Definition of Done**

- [x] Trace spans link request, event, delivery, attempt, webhook/executor/delegation, and replay lineage.
- [x] Metrics have bounded labels and avoid tenant-cardinality defaults unless explicitly enabled.
- [x] Dashboard and alert examples cover backlog age, dead rate, lease expiry, endpoint pause, command conflict, and delegation denial.
- [x] Secret/payload canary tests pass across logs, metrics, traces, exceptions, and evidence.
- [x] Observability remains optional and does not alter correctness behavior.

### - [ ] M13.07 — Complete security and supply-chain review

**Estimate:** 10–15 h
**Depends on:** M13.01–M13.06

**Goal**

Perform an internal adversarial review, obtain external review where possible, audit dependencies, generate an SBOM, and publish release provenance.

**Context**

RLS, SSRF, cryptographic key lifecycle, delegation, and evidence handling are high-risk boundaries that require review beyond unit tests.

**Affected files**

- `SECURITY.md`
- `docs/security-review/`
- `.github/workflows/security.yml`
- `.github/workflows/release.yml`
- `scripts/generate_sbom.py`

**Definition of Done**

- [x] Threat models are current for every advertised capability.
- [ ] Bandit, pip-audit, secret scanning, dependency review, and license checks pass or have documented accepted exceptions.
- [ ] SBOM and build provenance are attached to release artifacts.
- [ ] External or independent review findings have severity, owner, resolution, and disclosure status.
- [ ] No unresolved critical/high issue remains at RC promotion.

Bandit, pip-audit, the offline secret/license scan, and SBOM generation pass locally.
Dependency review, independent findings, provenance attachment, and promotion status
require the protected hosted release workflow.

### - [x] M13.08 — Validate backup restore and retention

**Estimate:** 7–10 h
**Depends on:** M13.02, M13.05

**Goal**

Exercise backup, point-in-time or logical restore, schema migration, retention, and incident procedures on production-like datasets.

**Context**

A reliable delivery system is incomplete when operators cannot recover its state or safely prune it. Restore must preserve identity and immutable history.

**Affected files**

- `docs/operations/backup-restore.md`
- `docs/operations/retention.md`
- `scripts/verify_restore.py`
- `tests/operations/test_retention_restore.py`

**Definition of Done**

- [x] Backup and restore preserve schema revision, event/delivery/attempt lineage, commands, subscriptions, secrets metadata, and handoffs.
- [x] Restored deployments pass doctor and the applicable real conformance profiles.
- [x] Retention is bounded, resumable, dependency-safe, and observable.
- [x] Key compromise, secret rotation, dead-letter surge, replay misuse, and failed migration runbooks are rehearsed.

Logical restore, protected identity comparison, live doctor/backlog checks, and every
applicable real conformance profile pass on PostgreSQL 16 and 18. Retention rehearses
1,000 terminal histories plus active and cross-tenant controls in batches of 128, with
dependency ordering and aggregate post-commit observations verified.

### - [ ] M13.09 — Complete documentation and deployment references

**Estimate:** 8–12 h
**Depends on:** M13.01–M13.08

**Goal**

Produce a coherent user journey from installation through secure production operation and incident response.

**Context**

The product category requires education. Documentation must explain transaction/effect boundaries, guarantee limits, database roles, and integration responsibilities better than isolated code examples.

**Affected files**

- `docs/`
- `examples/invoicing/`
- `examples/deployment/`
- `mkdocs.yml`
- `README.md`

**Definition of Done**

- [x] Quickstart reaches a real atomic handler delivery with PostgreSQL.
- [x] Tutorial covers signed webhook retry and deduplicating receiver.
- [x] Advanced guides cover Taskiq, command idempotency, and delegation when included in v1.
- [x] Operations cover roles/RLS, migrations, relay, keys, retention, backup, restore, observability, and incidents.
- [ ] Every executable-language Markdown block is inventoried and classified, but the
  database-backed journeys still need execution from the exact committed candidate
  artifacts in the protected workflow.

The maintained inventory covers 40 content-bound blocks and seven required journeys.
Syntax-only, manual/operator, and historical examples are explicitly distinct from
executed scenarios; local source-backed evidence is not promoted to hosted artifact
evidence.

### - [ ] M13.10 — Run the design-partner validation program

**Estimate:** External gate
**Depends on:** M9 beta; selected capabilities stable

**Goal**

Deploy the candidate with at least two external teams and capture structured evidence about correctness, usability, migration, operations, and category fit.

**Context**

The final point in the product and engineering assessment cannot be earned inside the reference repository. Production evidence is a v1 prerequisite.

**Affected files**

- `docs/planning/design-partner-protocol.md`
- `docs/planning/production-readiness-record.md`
- `docs/planning/known-limitations.md`

**Definition of Done**

- [ ] At least two external production deployments or equivalently serious live deployments are documented.
- [ ] Each partner runs doctor and applicable conformance profiles in its own environment.
- [ ] Migration, backup/restore, relay operation, retry/replay, and incident procedures are exercised.
- [ ] Feedback produces prioritized issues with disposition rather than informal notes.
- [ ] No unresolved contract-breaking behavior remains.

### - [ ] M13.11 — Build and observe the release candidate

**Estimate:** 8–12 h plus observation
**Depends on:** M13.01–M13.10

**Goal**

Package `1.0.0rc1`, publish complete evidence, and observe it under real deployment conditions before final release.

**Context**

The RC should freeze public API and schema unless a severe defect requires change. The observation period separates packaging success from operational stability.

**Affected files**

- `CHANGELOG.md`
- `docs/release-notes/1.0.0rc1.md`
- `.github/workflows/release.yml`
- `scripts/audit_release_candidate.py`

**Definition of Done**

- [ ] All mandatory runtime, compatibility, migration, security, conformance, package, Git, and extracted-archive gates pass.
- [ ] Release artifacts include checksums, SBOM, provenance, wheel, sdist, schemas, and certification reports.
- [x] RC documentation lists supported capabilities and explicit exclusions.
- [ ] Observation issues are triaged with release-blocking criteria.
- [ ] No public API or schema change occurs after RC without resetting the observation decision.

Tag and publication workflows now rerun quality, integration, security, package, readiness,
and cumulative real-runtime certification gates. RC and final-v1 readiness are distinct:
the RC gate requires partner/security evidence, while final promotion additionally requires
the completed, non-reset observation window and explicit two-approver go decision.

### - [ ] M13.12 — Approve and publish v1.0

**Estimate:** 4–6 h
**Depends on:** M13.11

**Goal**

Make the explicit go/no-go decision, publish `1.0.0`, and define the bounded post-v1 backlog.

**Context**

v1 is a compatibility and support commitment, not simply the next version number.

**Affected files**

- `CHANGELOG.md`
- `docs/release-notes/1.0.0.md`
- `docs/roadmap-post-v1.md`
- `.github/workflows/release.yml`

**Definition of Done**

- [ ] Two external production deployments and the RC observation gate are complete.
- [ ] No unresolved critical/high security or contract-breaking issue remains.
- [x] The complete real-runtime profile passes for every advertised optional capability.
- [ ] Migration and compatibility matrices are published and green.
- [ ] Release artifacts and trusted publication succeed from the protected tag.
- [x] Post-v1 work is demand-ranked and excludes workflows, non-PostgreSQL storage, sync support, or new adapters without evidence.

The cumulative adapter exercises all fourteen invariants in one report and binds its manifest
to package version, implementation commit, PostgreSQL/asyncpg versions, and installed schema
revisions. It passes locally on PostgreSQL 16 and PostgreSQL 18 with Redis Streams; hosted
matrix and protected-release execution remain the authoritative promotion evidence.

---

## Suggested first branch sequence

- `docs/record-runtime-baseline` — M8.01
- `build/restore-locked-toolchain` — M8.02
- `docs/freeze-runtime-decisions` — M8.03
- `feat/add-runtime-domain-models` — M8.04–M8.07
- `feat/add-postgres-core-schema` — M8.08–M8.10
- `feat/add-atomic-effect-store` — M8.11–M8.13
- `feat/add-leased-relay` — M8.14–M8.15
- `feat/add-handler-execution` — M8.16–M8.17
- `test/certify-core-runtime` — M8.18

## Immediate stopping rule

Do not begin M9 until the real PostgreSQL adapter—not the reference driver—passes the M8 `core`, `delivery`, and `security` gates on PostgreSQL 16 and 18. Do not begin M10–M12 merely because their conformance reference scenarios already exist.

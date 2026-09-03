# FastAPI-Mergen — Continuation Development Plan

**Date:** 2026-08-27  
**Current recoverable release:** `0.6.0a1`  
**Current Boundary Contract:** `1.0`  
**Planning horizon:** Milestones 8–13, through `1.0.0`  
**Assumption:** solo, part-time development at approximately 10 hours/week, with external review and design-partner time treated as schedule gates rather than coding estimates

## 1. Executive decision

Continue the library, but correct the repository baseline before adding another feature.

The current cumulative repository contains two real assets:

1. the verified Milestone 1 repository and API/specification foundation; and
2. the Milestone 7 implementation-independent Boundary Contract Conformance and Assurance Suite.

It does **not** contain the unavailable Milestone 2–6 runtime source. The PostgreSQL store and SQLAlchemy unit of work remain fail-closed Milestone 1 stubs, while the conformance suite certifies a reference in-memory driver. This is a valid assurance release, but it is not yet a usable transactional-effect runtime.

Therefore the continuation sequence is:

```text
restore the cumulative runtime
        ↓
certify the real runtime with Milestone 7
        ↓
ship the webhook MDP
        ↓
add one executor adapter
        ↓
add command idempotency
        ↓
add delegated MCP/API access
        ↓
production hardening and v1.0
```

The first rule of every future release is:

> A feature is advertised only when its production implementation—not merely the reference driver—passes the corresponding Boundary Contract profile against the supported infrastructure matrix.

## 2. Verified starting point

### 2.1 Implemented and retained

- `fastapi-mergen` distribution and `fastapi_mergen` import namespace;
- Python 3.11–3.14 metadata and typed-package marker;
- narrow public API spike;
- immutable `Principal`, typed `Event`, route-policy and retry-policy models;
- fail-closed `PostgresStore` and `MergenUnitOfWork` placeholders;
- Boundary Contract v1 descriptor;
- fourteen conformance invariants;
- six certification profiles: `core`, `delivery`, `security`, `webhook`, `executor`, and `complete`;
- deterministic reference driver and deliberate-fault oracle;
- JSON, JUnit, SARIF, and Markdown evidence;
- evidence redaction, bounded output, private atomic writes, and archived verification;
- packaging, Git-governance, and extracted-archive validation;
- current local result: 111 tests passed and 3 PostgreSQL-dependent tests skipped because no DSN was configured.

### 2.2 Not yet implemented in the cumulative repository

- real SQLAlchemy transaction ownership and `emit()` persistence;
- PostgreSQL event, delivery, attempt, subscription, command, or delegation tables;
- Alembic runtime migrations and schema compatibility logic;
- application/relay/migration database-role enforcement;
- live RLS diagnostics;
- polling relay, leases, retries, replay, or in-process handler execution;
- webhook subscriptions, encrypted secrets, signing, or SSRF-safe delivery;
- Taskiq handoff and worker bridge;
- transactional inbound command idempotency;
- audience-bound delegation and FastMCP integration;
- a real runtime adapter for the conformance suite;
- a committed, resolver-generated `uv.lock`;
- mandatory Ruff, mypy, Twine, and PostgreSQL 16/18 release gates.

### 2.3 Consequence for versioning

`0.6.0a1` remains an internal/pre-alpha **assurance baseline**. It should not be presented as cumulative runtime completion.

Future versions advance normally without fabricating missing history:

| Milestone | Target version | Public meaning |
|---|---:|---|
| M8 | `0.7.0a1` | Real core transactional runtime alpha |
| M9 | `0.8.0b1` → `0.8.0` | Webhook Minimum Differentiated Product |
| M10 | `0.9.0a1` | First external-executor adapter |
| M11 | `0.10.0a1` | Transactional command idempotency |
| M12 | `0.11.0a1` | Delegation and FastMCP integration |
| M13 | `1.0.0rc1` → `1.0.0` | Production-supported contract and runtime |

No release note may imply that the unavailable Milestone 2–6 Git history was recovered. The new runtime is implemented transparently on top of the preserved Milestone 1 and Milestone 7 history.

## 3. Product and architecture contract

### 3.1 Product definition

> **FastAPI-Mergen is the transaction boundary for tenant-safe side effects. It atomically records effect intent with an async SQLAlchemy business transaction, preserves tenant and authority provenance, and delivers the effect through independently retryable destinations.**

### 3.2 Required runtime invariants

Every supported implementation must preserve:

1. atomic intent;
2. tenant continuity;
3. explicit and non-expanding authority provenance;
4. stable retry identity;
5. independent fan-out state;
6. causal lineage;
7. accountable replay;
8. lease fencing;
9. context and resource cleanup;
10. secret minimization;
11. transactional command identity where enabled;
12. delegation audience and target binding where enabled;
13. webhook transport safety where enabled;
14. external-executor handoff correctness where enabled.

### 3.3 Supported technical boundary through v1.0

- async FastAPI only;
- async SQLAlchemy 2.x only;
- PostgreSQL 16–18;
- `asyncpg` as the first certified driver;
- one distribution: `fastapi-mergen`;
- one import root: `fastapi_mergen`;
- one console command: `fastapi-mergen`;
- one authoritative PostgreSQL schema: `fastapi_mergen`;
- polling as the correctness path;
- at-least-once delivery;
- exact event-type routing;
- typed event DTOs and bounded canonical payloads;
- Taskiq as the first external executor;
- FastMCP only as an integration consumer of the delegation boundary.

### 3.4 Explicit non-goals through v1.0

- no authentication or user-management system;
- no tenant provisioning, billing, membership, or dashboard product;
- no generic task queue;
- no workflow/DAG engine, timers, compensation, or human approval;
- no global ordering guarantee;
- no remote effect cancellation guarantee;
- no blind bearer-token forwarding;
- no schema-per-tenant or database-per-tenant orchestration;
- no synchronous SQLAlchemy;
- no non-PostgreSQL store;
- no second Python distribution;
- no hosted control plane or admin UI;
- no universal exactly-once claim.

## 4. Development and governance model

### 4.1 Branching

Use short-lived branches from `main`:

```text
feat/<3-5-word-name>
fix/<3-5-word-name>
test/<3-5-word-name>
docs/<3-5-word-name>
ci/<3-5-word-name>
chore/<3-5-word-name>
build/<3-5-word-name>
```

Every branch must be merged into `main` before milestone packaging. Preserve branches in milestone archives only when they are fully merged.

### 4.2 Commits and authorship

- author and committer: `mergen-institute` only;
- commit subjects: 3–7 words;
- one logical change per commit;
- tests and documentation belong in the same branch as the behavior they specify;
- no generated release artifact is committed unless the repository policy explicitly requires it;
- no rewritten or fabricated history for unavailable milestones.

### 4.3 Definition of complete

A work item is complete only when all applicable layers are complete:

```text
model/API
+ persistence/migration
+ security boundary
+ unit tests
+ live integration tests
+ conformance scenario
+ documentation
+ packaging/release behavior
```

Reference-driver certification alone is never sufficient evidence for a runtime feature.

### 4.4 Release gates

Mandatory for every advertised runtime release:

- clean `uv lock --check` and a committed resolver-generated `uv.lock`;
- Ruff lint and formatting;
- strict mypy;
- complete unit/security/conformance suite;
- PostgreSQL 16 and 18 integration tests;
- migration upgrade and downgrade tests;
- wheel and sdist build;
- Twine checks;
- clean base install and every advertised extra;
- Git authorship, branch, subject, ancestry, and object-integrity gates;
- extracted-ZIP rerun of the mandatory checks;
- no reachable `MilestoneNotImplementedError` on an advertised path;
- README, changelog, and package metadata matching actual capabilities.

## 5. Milestone roadmap

## Milestone 8 — Cumulative core runtime restoration

**Target:** `0.7.0a1`  
**Estimated effort:** 100–145 hours  
**Calendar:** 10–14 part-time weeks  
**Dependency:** current `0.6.0a1` assurance baseline

### Goal

Replace the fail-closed Milestone 1 runtime placeholders with a real, PostgreSQL-backed core engine and certify the implementation through the `core`, `delivery`, and `security` profiles.

### Deliverables

- truthful baseline/tag and corrected documentation;
- committed dependency lock and mandatory static/release tooling;
- immutable runtime event/delivery/attempt models;
- versioned canonical serialization and payload hashing;
- explicit outer SQLAlchemy unit of work;
- PostgreSQL schema, roles, grants, RLS, helper functions, and Alembic migration;
- atomic event publication and immutable route snapshots;
- event dedupe and payload-conflict behavior;
- claim/lease/finalize/reconcile repository;
- bounded polling relay and in-process handler sink;
- snapshot, revalidate, and service-policy authorization;
- fresh tenant-bound handler sessions;
- diagnostics and schema compatibility checks;
- real PostgreSQL conformance driver;
- invoicing vertical slice;
- PostgreSQL 16/18 and crash-boundary tests.

### Exit gate

- no runtime stubs remain on the advertised core path;
- business row, event, and original deliveries commit together or not at all;
- tenant A cannot access tenant B rows under the application role;
- pooled connections do not retain tenant or subject context;
- relay credentials cannot access configured application tables;
- stale workers cannot finalize a reclaimed delivery;
- the real runtime adapter certifies `core`, `delivery`, and `security` profiles;
- PostgreSQL 16 and 18 matrices pass;
- the invoicing example runs end to end with an in-process handler;
- `0.7.0a1` wheel and sdist pass clean-install and extracted-archive gates.

### Principal risks

- SQLAlchemy transaction ownership and implicit autobegin behavior;
- RLS role misconfiguration creating false confidence;
- dedupe races and route-snapshot drift;
- lease expiry ambiguity;
- the assurance API diverging from the real store.

## Milestone 9 — Webhook Minimum Differentiated Product

**Target:** `0.8.0b1`, then `0.8.0` after external validation  
**Estimated effort:** 75–105 hours  
**Calendar:** 7–10 part-time weeks  
**Dependency:** M8

### Goal

Ship the first marketable product boundary: a tenant-scoped transaction atomically creates signed webhook delivery intent, and the relay safely delivers, retries, dead-letters, and replays it.

### Deliverables

- tenant-scoped subscription and signing-secret schema;
- exact event-type subscription snapshotting in the originating transaction;
- AES-GCM secret envelope and lifecycle states;
- deterministic webhook wire envelope;
- Standard Webhooks-compatible signing and overlapping rotation;
- attempt-time DNS resolution and address classification;
- explicit validated-IP TLS transport with original-host SNI and authority;
- bounded redirects, timeouts, request/response sizes, and concurrency;
- deterministic HTTP-status and `Retry-After` classification;
- tenant-scoped operational API and CLI;
- replay, dead-letter, pause/reactivate, and retention operations;
- webhook conformance, security, and crash suite;
- deduplicating receiver and production-style demo.

### Exit gate

- the real webhook adapter certifies the `webhook` profile;
- exact signed bytes equal exact transmitted bytes;
- automatic retries retain message identity;
- manual replay creates a new linked message identity;
- private, loopback, link-local, metadata, mapped, mixed-answer, redirect, and rebinding cases fail closed;
- response bodies and secrets do not enter persistence, logs, metrics, exceptions, or evidence;
- receiver-success/relay-crash creates multiple attempts but one deduplicated consumer effect;
- one design partner runs the flow in serious staging or production-like conditions.

## Milestone 10 — Taskiq external-executor adapter

**Target:** `0.9.0a1`  
**Estimated effort:** 40–60 hours  
**Calendar:** 4–6 part-time weeks  
**Dependency:** M8; M9 recommended but not technically required

### Goal

Add one external executor without making Taskiq a second reliability authority or turning Mergen into a queue framework.

### Deliverables

- integrity-protected per-attempt handoff model;
- durable handoff table and migration;
- stable Taskiq task IDs;
- enqueue-as-nonterminal semantics;
- worker-side claim and execution fencing;
- principal restoration and fresh tenant-bound application session;
- Mergen-controlled retry/dead-letter decisions;
- expired-handoff reconciliation;
- real Taskiq conformance adapter and duplicate-delivery tests;
- optional `taskiq` extra and operations documentation.

### Exit gate

- the real Taskiq adapter certifies the `executor` profile;
- broker acceptance never marks the Mergen delivery successful;
- concurrent duplicate broker messages produce at most one active handler execution;
- stale workers cannot finalize newer work;
- sequential jobs for different tenants show no principal, session, or dependency leakage;
- ambiguous external-effect crash semantics are documented and retain stable dedupe identities.

## Milestone 11 — Transactional inbound command idempotency

**Target:** `0.10.0a1`  
**Estimated effort:** 45–65 hours  
**Calendar:** 5–7 part-time weeks  
**Dependency:** M8

### Goal

Prevent duplicate committed application commands by binding command identity, business writes, and a bounded replayable response to one outer SQLAlchemy transaction.

### Deliverables

- opaque key validation and SHA-256 key digest;
- strict request fingerprint format;
- command-generation schema, RLS, and immutability trigger;
- transaction-scoped advisory-lock serialization;
- explicit command context and response completion contract;
- safe response capture and replay;
- FastAPI request preparation and bounded error mapping;
- expiry and bounded pruning;
- concurrency, rollback-window, fingerprint-conflict, and subject-conflict tests;
- real command-idempotency conformance driver.

### Exit gate

- identical concurrent requests commit one business transaction and replay one response;
- rollback leaves no durable claim;
- key reuse with different fingerprint or subject fails with bounded conflict;
- raw keys and unsafe response headers never persist or appear in evidence;
- streaming, cookie-setting, credential-bearing, oversized, and unsupported responses fail closed;
- PostgreSQL 16/18 concurrency tests pass.

## Milestone 12 — Delegation and FastMCP integration

**Target:** `0.11.0a1`  
**Estimated effort:** 45–65 hours  
**Calendar:** 5–7 part-time weeks  
**Dependency:** M8; a concrete design-partner use case

### Goal

Preserve tenant, subject, actor, client, and attenuated authority across an MCP-to-FastAPI or internal-API boundary without forwarding the caller’s original bearer credential.

### Deliverables

- versioned delegation credential and key-ring protocols;
- audience, method, canonical path, scope, lifetime, and delegation-depth binding;
- key rotation and revocation;
- FastMCP bridge using trusted caller metadata;
- downstream FastAPI verification dependency;
- component-discovery policy separated from route authorization;
- token-free delegation audit records;
- ambiguous-target and path-normalization hardening;
- real delegation conformance adapter and security suite;
- optional `fastmcp` extra and integration guide.

### Exit gate

- no raw inbound authorization, cookie, or session credential is forwarded or persisted;
- delegated scopes are a strict subset of verified parent authority and route allowance;
- exact audience, method, and canonical target mismatches fail closed;
- revoked keys fail immediately and retiring keys follow bounded overlap policy;
- route authorization remains mandatory even when tool discovery hides unavailable tools;
- the real delegation adapter passes its security and conformance scenarios.

## Milestone 13 — Production hardening and v1.0

**Target:** `1.0.0rc1`, then `1.0.0`  
**Estimated engineering effort:** 90–130 hours plus external deployment time  
**Calendar:** 9–13 part-time weeks, excluding design-partner observation  
**Dependency:** M8–M12 as selected for the v1 support promise

### Goal

Convert the working pre-1.0 system into a stable, supportable release with a tested migration story, explicit compatibility contract, production operations, independent security review, and real deployment evidence.

### Deliverables

- frozen v1 public API and compatibility policy;
- schema migration path from every published alpha/beta revision;
- upgrade, downgrade, backup, restore, retention, and incident runbooks;
- complete PostgreSQL 16/18 and Python 3.11–3.14 matrix;
- minimum and latest dependency jobs;
- asyncpg certification and evaluated async-psycopg support decision;
- load, fairness, backlog, retention, and failure-recovery benchmarks;
- OpenTelemetry traces, metrics, and structured logging;
- security review, dependency audit, SBOM, provenance, and release signing;
- complete real-runtime conformance certification;
- two external production deployments or equivalent evidence;
- stable reference application and deployment templates;
- release-candidate observation window and documented issue-resolution criteria.

### Exit gate

`1.0.0` is allowed only when all are true:

- at least two external production deployments exist;
- no known critical or high-severity unresolved security issue exists;
- the migration matrix passes from every supported released schema revision;
- backup and restore have been exercised on production-like data;
- the real cumulative runtime passes the `complete` profile for every advertised optional capability;
- public API and evidence schemas have documented compatibility guarantees;
- incident, key-rotation, dead-letter, replay, retention, and credential-compromise procedures are documented and rehearsed;
- the release candidate has completed an observation period without a contract-breaking defect.

## 6. Cross-cutting workstreams

### 6.1 Conformance integration

- keep the reference driver as an oracle and deliberate-fault fixture;
- add real adapters incrementally rather than one oversized adapter;
- bind every report to package version, schema revision, implementation commit, database version, driver version, profile, and manifest digest;
- distinguish `CERTIFIED`, `FAILED`, `SKIPPED`, and `NOT_RUN` rigorously;
- never let a reference report satisfy a runtime release gate.

### 6.2 Database and migration discipline

- one schema-revision registry independent of package version;
- no runtime auto-migration;
- migration owner never used by requests or relay;
- every migration has upgrade, downgrade, ownership, grant, RLS, and search-path tests;
- destructive or data-rewriting changes require an ADR and dry-run procedure;
- retention and pruning are bounded and tenant-safe.

### 6.3 Security

- threat-model update for every new trust boundary;
- raw credentials and plaintext secrets forbidden in durable rows and default evidence;
- database roles tested live, not inferred only from DDL text;
- network security tested against hostile DNS and HTTP fixtures;
- error and evidence payloads bounded and control-character safe;
- external review before public beta and again before v1.0.

### 6.4 Observability

Every runtime capability emits vendor-neutral events for:

- event publication;
- delivery claim and lease loss;
- attempt result and retry scheduling;
- backlog age and due count;
- dead-letter and replay;
- webhook endpoint pause/reactivation;
- executor handoff and worker claim;
- command claim/replay/conflict;
- delegation issue/verify/deny;
- RLS/schema diagnostics.

Payload content, secrets, raw tokens, and response bodies are excluded by default.

### 6.5 Documentation and adoption

Before `0.8.0`:

- publish a full async FastAPI + SQLAlchemy + PostgreSQL RLS guide;
- publish the Boundary Contract separately from the implementation;
- provide one production-style invoicing deployment;
- recruit at least two design partners;
- document exactly what Mergen does not guarantee.

Before `1.0.0`:

- publish migration and incident case studies;
- document real operational limits and benchmark methodology;
- maintain a compatibility table based on executed tests, not intentions;
- use production users and incidents—not stars—as continuation metrics.

## 7. Critical path

```text
M8 core runtime
  ├──> M9 webhook MDP ──> public beta / design partner
  ├──> M10 Taskiq adapter
  ├──> M11 command idempotency
  └──> M12 delegation (demand-gated)

M9 + selected M10–M12 + external deployment evidence
  └──> M13 production hardening and v1.0
```

M10, M11, and M12 may overlap after M8 only when they have separate maintainers or branches and do not delay the M9 marketable MDP. For solo development, execute them sequentially.

## 8. Risk register and decision gates

| Risk | Severity | Control |
|---|---:|---|
| Assurance suite advances faster than runtime | Critical | Runtime profiles must execute real paths; reference certification cannot release runtime features |
| Missing Milestone 2–6 source creates false continuity | Critical | Preserve provenance statement; implement new history transparently; no fabricated commits |
| RLS is configured but ineffective | Critical | Live role probes, owner/BYPASSRLS checks, FORCE RLS, pooled-connection tests |
| Duplicate external effects surprise users | High | At-least-once language, stable IDs, dedupe examples, ambiguous-crash tests |
| Webhook SSRF bypass | High | Explicit-IP transport, hostile DNS fixtures, external security review, egress controls |
| Relay becomes overprivileged | High | Dedicated schema grants and live denial tests on application tables |
| Scope expands into workflows | High | Feature-admission test and explicit v1 non-goals |
| Migration history becomes unstable | High | Revision registry, upgrade/downgrade matrix, no auto-migration |
| Optional integrations fragment packaging | Medium | One distribution and extras only through v1 |
| Solo schedule slips | Medium | M9 MDP takes priority; M10–M12 are demand-gated |
| No market adoption | High | Design-partner gates before beta and v1; pivot to assurance suite if runtime adoption fails |

### Stop or pivot conditions

- Stop M8 expansion when the core runtime cannot pass its real PostgreSQL conformance profile without changing the frozen Boundary Contract; resolve the contract/runtime mismatch first.
- Stop before M10–M12 when no third party runs the M9 MDP in serious staging within twelve weeks of beta.
- Drop M12 when a trusted upstream framework provides an equivalent principal-preserving, target-bound delegation boundary.
- Pivot toward the Boundary Contract and Assurance Suite when users consistently value certification and diagnostics more than the embedded runtime.

## 9. Recommended immediate sequence

1. Commit `plan.md` and `todo.md` on `docs/continue-development`.
2. Tag or otherwise record the `0.6.0a1` assurance baseline.
3. Open `feat/restore-core-runtime` only after the M8 schema/API ADR review passes.
4. Make `uv.lock`, Ruff, mypy, Twine, and PostgreSQL 16/18 available as mandatory—not optional—M8 gates.
5. Implement one vertical slice first:

```text
authenticated tenant request
→ explicit UoW
→ invoice row + event + handler delivery commit
→ relay claim
→ fresh tenant-bound handler session
→ lease-token finalization
→ real core/delivery/security conformance report
```

6. Add webhooks only after this vertical slice passes crash and isolation tests.

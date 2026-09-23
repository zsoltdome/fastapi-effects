# Changelog

All notable changes are documented here. The project follows Semantic Versioning,
with explicit pre-1.0 contract and evidence-schema notes.

## Unreleased

## 0.11.0a2 - 2026-09-23

### Added

- Required exact-public-`0.11.0a1`-wheel to exact-candidate-wheel upgrade evidence on
  PostgreSQL 16 and 18, covering seeded data, ownership, roles, grants, forced RLS,
  constraints, indexes, Alembic revisions, and component revision markers.
- Real PostgreSQL webhook key-lifecycle coverage for revoked and expired-retiring keys,
  wrong-tenant access, terminal-finalization interruption, sibling progress, and
  immutable attempt history.
- Live control-boundary backend-loss tests and a PostgreSQL wire-protocol proxy that
  drops commit acknowledgements only after the server reports completion.
- Candidate-bound persistent PostgreSQL 16/18 restart reports, signal shutdown checks,
  Taskiq duplicate-worker coverage, and durable release-asset retention.
- A narrow PostgreSQL/signed-webhook release-scope ADR, numeric validator inventory,
  and published-package-first version-matched consumer quickstart.

### Changed

- Relay polling, control-plane, finalization, and shutdown timing configuration now
  rejects non-finite values, booleans, nonnumeric inputs, and out-of-range values at
  construction time. The documented `(0, 60]` and `(0, 300]` bounds and defaults are
  unchanged.
- Webhook transport and HTTP response timeout configuration now applies explicit
  finite-number and type checks. Webhook retention and Taskiq worker/recovery numeric
  controls reject booleans and wrong runtime types through the configuration-error
  path.
- Release manifests require historical-upgrade and PostgreSQL 16/18 restart evidence
  for every post-`0.11.0a1` candidate while preserving verification of the historical
  baseline artifact.
- The release and publish paths use approval-gated, tag-restricted environments; `main`
  and release tags are protected, and publication promotes and archives only the exact
  selected evidence artifact.

### Security

- T05 and T09 evidence now covers cross-tenant key denial, backend termination at
  reconciliation/claim/finalization boundaries, stale-finalizer rejection, and
  server-committed/client-unknown outcomes without claiming exactly-once delivery.
- Private vulnerability reporting is enabled. The repository remains single-owner, so
  independent review, two external deployments, RC observation, and two-person stable
  approval remain open.

## 0.11.0a1 - 2026-09-20

### Added

- Real async SQLAlchemy outer unit of work with transaction-local tenant and subject
  context.
- PostgreSQL event, delivery, attempt, and schema-revision mappings with forced RLS.
- Atomic immutable fan-out, tenant-scoped dedupe, payload-conflict detection, fenced
  leases, full-jitter retry, reconciliation, replay, and polling relay.
- Fresh tenant-bound in-process handler execution with snapshot, revalidation, and
  service-policy authority.
- Live `doctor` role/RLS/schema/context diagnostics and Alembic migration round trips.
- Production PostgreSQL conformance adapter for `core`, `delivery`, and `security`.
- Target-bound short-lived delegation signing and verification primitives required by
  the preserved security profile.
- Immutable webhook subscription versions, forced-RLS secret storage, and AES-GCM
  envelope encryption with one-time secret creation and bounded rotation overlap.
- Standard Webhooks-compatible deterministic envelopes and multi-key signatures.
- Hostile URL/DNS policy, explicit-IP TLS transport, bounded HTTP/1.1 parsing,
  Retry-After classification, operational replay/retention, and auditable auto-pause.
- PostgreSQL-backed webhook conformance driver, ambiguous-crash coverage, and a
  deduplicating receiver example.
- Durable Taskiq handoff rows, stable per-attempt task IDs, nonterminal broker
  acknowledgement, duplicate execution fencing, principal/session restoration,
  execution-token finalization, expiry recovery, and real executor conformance.
- Transaction-owned command generations, advisory-lock serialization, strict request
  fingerprints, immutable bounded response replay, forced RLS, restricted pruning,
  FastAPI helpers, and real command conformance.
- Short-lived audience/method/path-bound delegation, non-expanding scope/depth,
  bounded rotation/revocation, token-free audit, downstream FastAPI enforcement,
  a FastMCP 3.4 bridge, and real delegation conformance.
- Frozen v1 public-surface inventory, stable exception codes, schema component registry,
  explicit startup compatibility checks, data-preserving migration matrix, and guarded
  destructive downgrades.
- Tenant-bound, security-definer webhook retention with bounded dependency-ordered
  batches, post-commit telemetry, and schema revision `0005_webhook_retention`.

### Changed

- Renamed the project and distribution to FastAPI Effects / `fastapi-effects`, with
  Zsolt Döme as the package author. The import package, Python API names, PostgreSQL
  schema and roles, telemetry, environment variables, protocol identifiers, examples,
  and command now consistently use the `fastapi_effects` namespace. This is an
  intentional breaking change to the pre-release alpha surface.
- Version advanced to the delegation/FastMCP alpha `0.11.0a1`.
- The invoicing example now completes request → atomic publication → relay →
  tenant-bound handler end to end.
- Taskiq worker admission now rejects handoffs from reclaimed attempts before handler
  execution; relay lease loss is isolated per delivery.
- Retry elapsed time is a latest-finish deadline enforced during scheduling, claim,
  reconciliation, webhook/handler execution, Taskiq admission/enqueue, and finalization;
  expired leases cannot finalize before reconciliation.
- Webhook attempts now share one aggregate dependency/network/cleanup budget, validate
  production TLS contexts, validate the complete DNS answer set before bounding address
  attempts, and consume informational HTTP responses before classifying the final
  response.
- Tenant webhook replay now uses an atomic insert-from-terminal-source path that works
  with the application role's least-privilege `SELECT, INSERT` grant.
- The webhook router now resolves its closure-scoped FastAPI dependencies correctly;
  replay and management endpoints no longer treat injected principal/session values as
  required query fields.
- Historical revisions now use immutable versioned DDL/security definitions, protected
  by migration-matrix and golden-contract tests.
- RC/final readiness auditing is phase-aware and validates candidate-bound partner,
  review, observation, issue, digest, and approval evidence instead of truthy placeholders.
- The shared release check selects its readiness phase automatically, allowing populated
  RC/final records to reach their applicable gate.
- Git governance preserves the exact documented recovery-baseline provenance exception
  while continuing to enforce current identity and subject rules for later commits.
- The local release gate now passes only wheel and sdist files to Twine, so metadata
  such as `dist/.gitignore` cannot create a false artifact-validation failure.
- Documentation and capability evidence paths must resolve inside the repository, and
  ledger source, timestamp, lock, and artifact bindings receive structural validation.

### Documentation

- Recorded commit `6b8d3626445bd577cc6c5af80f3b84e30e2c7712` as the truthful
  assurance baseline for the new cumulative runtime implementation.
- Clarified that the Milestone 2–6 runtime source was unavailable and is being newly
  implemented rather than historically reconstructed.

## 0.6.0a1 - 2026-08-26

### Added

- Boundary Contract v1 executable conformance package.
- Strict capability manifests and `core`, `delivery`, `security`, `webhook`,
  `executor`, and `complete` profiles.
- Nineteen deterministic scenarios and twenty injected reference faults.
- JSON, JUnit, SARIF, and Markdown evidence reporters.
- Strict report parsing, report digests, and manifest-bound archived verification.
- Deployment secret-canary checks and private atomic report output.
- Conformance CLI, reference driver, testing assertion helper, JSON schemas, CI, ADR,
  operator documentation, and Milestone 7 audit.

### Changed

- Package version advanced from the Milestone 1 foundation to the independent
  assurance release.
- Boundary Contract documentation expanded from seven MDP invariants to fourteen
  cross-milestone invariants.

### Security

- Public evidence omits exception messages and recursively redacts sensitive fields.
- Manifest metadata rejects sensitive field names.
- Report output refuses symbolic links and defaults to mode `0600`.

`0.6.0a1` is an implementation-independent assurance release, not a production
transactional-effect runtime.

## 0.0.1 - 2026-08-24

### Added

- Milestone 1 repository and packaging foundation.
- Boundary Contract v0.1, threat model, and architecture decision records.
- Provisional public API that fails safely before Milestone 2 behavior.
- PostgreSQL integration harness and clean-artifact CI design.
- Invoicing reference application skeleton.

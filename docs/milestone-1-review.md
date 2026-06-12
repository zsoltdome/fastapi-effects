# Milestone 1 implementation review

**Milestone:** Specification and repository foundation  
**Repository version:** `0.0.1`  
**Review date:** 2026-08-24  
**Implementation owner:** `mergen-institute`  
**Decision:** **implementation complete; external matrix certification pending first CI run**

## 1. Scope of this sign-off

Milestone 1 freezes the Boundary Contract, public API shape, trust model, durable-data
semantics, repository structure, packaging gates, PostgreSQL test harness, and reference
application. It deliberately does **not** implement event persistence, RLS migrations,
relay execution, handler execution, or webhook delivery. Every provisional runtime path
that would imply those Milestone 2 or Milestone 3 guarantees fails before application SQL.

This review distinguishes two states:

- **implemented:** the repository contains the required code, documentation, tests, and CI
  jobs;
- **certified:** the relevant job has actually executed in a suitable environment.

The current execution environment had Python 3.13 and the required application runtime
packages, but no container runtime, PostgreSQL client/server, Ruff, mypy, or outbound
package-index access. Therefore PostgreSQL 16/18, Python 3.11–3.14, minimum-dependency,
Ruff, mypy, and fully network-isolated extras checks are implemented in CI but are not
claimed as locally certified.

## 2. Milestone exit gate

| Exit condition | Status | Evidence |
|---|---|---|
| Event/delivery identity, route snapshots, dedupe, replay, RLS trust, authorization, and lease behavior are unambiguous | **Complete** | Boundary Contract, five ADRs, data-model reference, route-snapshot schema, UoW lifecycle, failure taxonomy, and conformance map |
| API spike compiles, boots, and reaches no application SQL when Milestone 2 behavior is requested | **Complete** | `tests/unit/test_public_api_spike.py`, `tests/unit/test_error_safety.py`, reference-app boot tests |
| Clean source/wheel import and optional-feature boundaries are exercised | **Locally certified for base wheel; CI certification pending for all extras/sdist** | `scripts/build_and_test_artifacts.py`, packaging tests, Package workflow |
| PostgreSQL 16 and 18 environment exists with migration, app, relay, and misconfigured roles | **Implemented; CI certification pending** | `compose.yaml`, disposable role/database fixtures, pairwise PostgreSQL CI jobs |
| Remaining implementation work is represented in M2/M3 backlog | **Complete** | M2: 100–130 h; M3: 80–110 h; combined 18–22 part-time weeks, within the 21–26 week MDP envelope including M1 and reserve |

No semantic design blocker remains for Milestone 2. External certification failures must
block a release and be fixed on a short `fix/...` branch before persistence work proceeds.

## 3. Work-item audit

### M1.01 — Repository and governance

**Status:** Complete.

- Single Git repository with `main` plus typed short-lived branches.
- Branch slugs and commit subjects contain three to seven short words.
- Git author and committer name/email are checked across all local branches.
- Only `mergen-institute <mergen-institute@users.noreply.github.com>` is permitted.
- Contribution, security, changelog, editor, ignore, and dependency-update policies exist.

### M1.02 — Packaging contract

**Status:** Complete.

- Distribution: `fastapi-mergen`.
- Import root: `fastapi_mergen`; occupied `mergen` root is rejected by gates.
- Console entry point: `fastapi-mergen`.
- One authoritative version module exposes `fastapi_mergen.__version__`.
- One distribution uses base dependencies plus `webhooks` and `otel` optional extras.
- Wheel includes `py.typed`; project metadata declares Python 3.11–3.14 and pre-alpha status.

### M1.03 — Quality conventions

**Status:** Implemented; static-tool execution pending CI in this environment.

- Ruff formatting/linting, strict mypy, strict pytest markers/configuration, and warnings-as-errors are committed.
- `uv run python scripts/check.py` is the canonical full quality command.
- Async tests use pytest-asyncio auto mode with function-scoped event loops.
- No mutable principal, route, or database fixture is shared between tests.

A generated `uv.lock` is intentionally not fabricated offline. The first networked quality
run will generate and review it; until then CI resolves within explicit lower/upper bounds.
A lockfile becomes mandatory before the first public alpha tag.

### M1.04 — CI and artifact matrix

**Status:** Complete as implementation; external matrix execution pending CI.

- Quality matrix covers Python 3.11, 3.12, 3.13, and 3.14.
- Minimum-direct-dependency job uses `lowest-direct` resolution.
- PostgreSQL pairwise matrix covers Python 3.11/PostgreSQL 16 and Python 3.14/PostgreSQL 18.
- Package job builds and clean-installs base wheel, both extras, and source distribution.
- Base-environment checks verify optional dependencies are absent.
- Release-only publishing uses trusted-publishing/OIDC permissions and cannot run on pull requests.
- Third-party GitHub Actions are pinned to immutable commit SHAs.

### M1.05 — Boundary Contract

**Status:** Complete.

The seven normative invariants are frozen as BC-01 through BC-07. The guarantee vocabulary
separates atomic local commit, at-least-once delivery, stable automatic-retry identity,
consumer-assisted effectively-once behavior, and accountable manual replay. Ordering and
cancellation are explicitly unsupported in the MDP.

### M1.06 — Threat model

**Status:** Complete.

The model covers tenant spoofing, cross-tenant reads/writes, role bypass, pool leakage,
relay over-privilege, stale workers, authorization revocation, replay abuse, credential
leakage, webhook SSRF, route drift, and dependency compromise. Controls map to future
conformance or chaos tests, with residual risks recorded.

### M1.07 — Explicit UoW

**Status:** Complete.

The UoW ADR fixes outer transaction ownership, tenant binding before application SQL,
commit/rollback responsibility, cancellation behavior, finalizer behavior, nested-UoW
rejection, and savepoint semantics. The Milestone 1 stub raises before SQL rather than
simulating atomic persistence.

### M1.08 — Event, delivery, and attempt model

**Status:** Complete.

The schema reference separates immutable event intent, independently retryable deliveries,
and append-only attempts. It fixes composite tenant-safe foreign keys, canonical payload
hashes, dedupe conflict behavior, stable retry identity, replay generations, retention, and
redaction boundaries.

### M1.09 — Route and authorization snapshots

**Status:** Complete.

Routes are exact, deterministically ordered, versioned, and frozen at startup. Only the
highest registered version of each stable route key is active for new emissions; older
handler versions remain executable for already-snapshotted deliveries. A stable route key
cannot change event type. Delivery snapshots contain serializable destination, retry, and
authorization data—never Python callables, raw credentials, or plaintext secrets. Snapshot,
revalidate, and service-policy formulas are normative and authority cannot silently expand.

### M1.10 — Relay state machine

**Status:** Complete.

The ADR fixes short claim transactions, `FOR UPDATE SKIP LOCKED`, fresh lease tokens,
attempt creation at claim, commit-before-I/O, compare-and-set finalization, lease recovery,
retry/dead-letter transitions, full-jitter backoff, bounded tenant fairness, and a kill-point
matrix. Handler or network I/O while claim locks are held is prohibited.

### M1.11 — Public API spike

**Status:** Complete.

The spike includes immutable `Principal`, typed `Event`, route/handler registration,
`RetryPolicy`, authorization modes, `EffectContext`, explicit `MergenUnitOfWork`, narrow
protocols, and a public exception taxonomy. Exact routes, active-version selection, and
duplicate/downgrade/freeze checks execute; persistence-dependent calls fail closed.

### M1.12 — PostgreSQL test environment

**Status:** Implemented; live execution pending CI.

- Compose profiles provide PostgreSQL 16 and 18.
- Every test receives a unique database and random role credentials.
- Fixtures create migration-owner, app, relay, and intentionally `BYPASSRLS` roles.
- Cleanup force-drops the database and roles after success or failure.
- Tests verify role flags, server version, database identity, and application-schema denial.

### M1.13 — Reference app and architecture gate

**Status:** Complete, with PostgreSQL-backed boot certification pending CI.

The invoicing app renders OpenAPI and demonstrates trusted principal ingress, async session
wiring, an application model, DTO event, exact route declaration, handler shape, and an
explicit UoW. It imports only planned public APIs. `scripts/architecture_gate.py` and
`scripts/verify_milestone_one.py` prevent scope growth, API leakage, missing ADRs, naming
collisions, incomplete contracts, unsafe workflow drift, and non-compliant Git metadata.

## 4. Validation record

### Executed successfully in this environment

```text
python -m compileall -q src examples scripts tests
python -m pytest -q -m "not integration"
# 24 passed, 4 deselected

python scripts/architecture_gate.py
# Milestone 1 architecture gate passed

python scripts/verify_milestone_one.py
# Milestone 1 structural verification passed

python scripts/build_and_test_artifacts.py --offline-system-packages
# wheel + sdist built; base wheel clean-installed and imported

git diff --check
git fsck --full
```

### Required first-CI certifications

```text
ruff format --check .
ruff check .
mypy
pytest -q -m integration       # PostgreSQL 16 and 18 matrix
python scripts/build_and_test_artifacts.py  # clean base/extras/sdist with networked resolver
```

Failures in any of these jobs revoke this sign-off until corrected. They are not deferred
feature work.

## 5. Frozen decisions for Milestone 2

Milestone 2 must preserve the following decisions unless a superseding ADR is accepted:

1. PostgreSQL RLS is the only MDP isolation mode.
2. `mergen_migration_owner`, `mergen_app`, and `mergen_relay` are separate roles.
3. Handlers never receive the relay control connection.
4. The Mergen UoW owns the outer transaction and rejects pre-existing transactions.
5. Business changes, event, and route-derived deliveries commit atomically.
6. Event, delivery, and attempt are separate durable entities.
7. Automatic retry keeps delivery identity; manual replay creates linked new identity.
8. Delivery is at least once; generic exactly-once effects are not promised.
9. Route and authorization policy snapshots are immutable.
10. Lease-token compare-and-set is required for renew/finalize operations.
11. No handler or network I/O occurs while claim locks are held.
12. Queue adapters, MCP, inbound idempotency, workflows, ordering, and cancellation remain out of scope.

## 6. Remaining questions

| Question | Owner | Blocking? | Resolution gate |
|---|---|---:|---|
| Exact dependency lock after a networked resolver run | `mergen-institute` | No for M1 ZIP; **yes before public alpha** | Review generated `uv.lock` in first CI-enabled dependency PR |
| Actual PostgreSQL 16/18 fixture behavior | `mergen-institute` | **Yes before M2 persistence merge** | Both integration matrix jobs pass |
| Ruff/mypy findings under supported Python matrix | `mergen-institute` | **Yes before M2 persistence merge** | All quality jobs pass |
| First external design-partner API review | product owner | No for M1; yes for M2 exit | M2 design-partner gate |

## 7. Sign-off

**Milestone 1 implementation is signed off.** The repository is ready for the first
networked CI run and then Milestone 2 implementation, subject to the explicit first-CI
gates above. No unverified external gate is represented as having passed locally.

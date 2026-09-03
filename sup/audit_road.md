# FastAPI-Mergen — Codebase audit and development roadmap

**Audit date:** 7 September 2026  
**Snapshot:** `FastAPI-Mergen-main(1).zip`  
**Declared package version:** `0.11.0a1`  
**Planning sources:** [`plan.md`](plan.md) and [`todo.md`](todo.md). The original
supplied names were `plan(8).md` and `todo(8).md`.  
**Decision:** continue development; retain alpha status; prioritize correctness repairs and verified adoption rather than adding capabilities.

**Remediation status (8 September 2026):** F01–F18 now have local regression evidence
at the committed local-verification source, and the companion
[`remediation.md`](remediation.md) records the
acceptance-level disposition. This audit remains the historical snapshot assessment;
candidate-bound hosted checks, independent review, external deployments, and RC
observation remain open and still block promotion.

## 1. Executive assessment

FastAPI-Mergen is no longer the Milestone 1/Milestone 7 assurance-only baseline described in the opening of the supplied continuation plan. The archive contains substantial implementations of the PostgreSQL transactional runtime, leases and relay, tenant-bound handlers, webhooks, Taskiq handoffs, command idempotency, delegation, migrations, diagnostics, observability, and production-oriented verification tooling.

This is a meaningful implementation, not a collection of empty placeholders. The core decomposition is worth preserving. A rewrite or another round of feature expansion would be the wrong next move.

However, the assertion that only external review, partner evidence, and release governance remain is too strong. The audit found engineering issues affecting stale-worker admission, relay liveness, attempt deadlines, application-role replay, HTTP handling, TLS configuration, migration stability, and the final release path. Eight offline diagnostic probes reproduced unsafe behavior in production methods or release scripts. The database and network boundaries in those probes are test doubles; they are not claims of live PostgreSQL, Redis, or TLS certification.

**Readiness judgement:** suitable for continued engineering and carefully controlled testing; not ready for an unrestricted production-support promise, RC promotion, or v1. A core/webhook beta is a credible next product milestone after the applicable defects are repaired and verified against real infrastructure. Existing optional integrations can remain available as experimental capabilities; their presence should not expand the first stable support promise automatically.

### What I would preserve

Preserve the single distribution/import root, explicit outer transaction ownership, separate event/delivery/attempt identities, tenant and principal provenance, snapshotted routing, at-least-once guarantee language, real-adapter versus reference-oracle distinction, and the two-partner/independent-review/RC-observation gates. These are the right architectural and governance commitments for the product described in `plan.md:95–149` and `403–441`.

### What I would change immediately

Replace the obsolete baseline in the live plan, reopen affected checklist guarantees, establish regression tests for the findings below, repair reliability and permission boundaries, and make release checks phase-aware. Do not describe a checked engineering task, a historical JSON result, or a reference certification as independent proof that the current deployment is safe.

## 2. Scope and verification method

### 2.1 Source identity and size

Archive SHA-256: `14db08002daa8771699d03b925dbccba46e5a39857db4a637818ebb2e3039fb0`.

| Area | Python files | Physical Python lines |
|---|---:|---:|
| Package source | 128 | 17,849 |
| Tests | 87 | 7,427 |
| Examples | 17 | 539 |
| Scripts | 23 | 3,182 |
| **Total** | **255** | **28,997** |

These counts describe the supplied snapshot, not code quality or coverage. The archive has no `.git` directory, so authorship, ancestry, branch merges, object integrity, protected hosted checks, and actual published releases could not be established from it. That is a limitation of the artifact, not by itself a repository defect.

The review concentrated on transaction and authority boundaries, delivery state transitions, failure handling, webhook transport, executor admission, migrations/grants, test evidence, packaging, and release governance. It was not an exhaustive formal proof or a substitute for independent security review. No repair was applied to the supplied code. Builds were performed in a separate working copy.

### 2.2 Checks independently executed

| Check | Observed result | Interpretation |
|---|---|---|
| Dependency synchronization | Failed to download build dependencies because container DNS/network resolution failed | A locked supported environment was not installed |
| Initial non-integration/non-packaging pytest selection | Collection failed in six modules importing unavailable optional dependencies | No full-suite result |
| Available selection after excluding those six modules | **218 passed, 1 failed, 42 deselected** | The failure is the installed FastAPI version assertion, not a demonstrated runtime defect |
| Architecture gate | Passed | Import/architecture check only |
| Source/example/script compilation | Passed | Syntax check only |
| Documentation smoke script | Passed | Compiles Python examples and executes three selected CLI commands |
| Milestone 13 local audit | Passed | Repository-scaffolding/historical-evidence validation, not proof that the new findings are absent |
| Reference `complete` conformance | **19 scenarios passed** | Certification of the reference oracle, not the production PostgreSQL runtime |
| Direct wheel and sdist build | Passed | Non-isolated setuptools backend build, not Twine or clean-install certification |
| Offline adversarial probes | **8 behaviors reproduced** | Real methods/scripts with explicit DB/network doubles or synthetic readiness data |

The environment used Python 3.13.5, FastAPI 0.128.2, Starlette 0.50.0, SQLAlchemy 2.0.50, and Pydantic 2.13.4. The archive requires FastAPI `>=0.141,<0.142` and Starlette `>=1.0.1,<2`. The single available-suite failure was `tests/compatibility/test_matrix_contract.py:23`, which correctly notices the FastAPI mismatch. The unsupported environment means even the passing subset is supporting evidence, not a release gate.

Missing dependencies included `asyncpg`, `taskiq`, `taskiq-redis`, `fastmcp`, and `standardwebhooks`. PostgreSQL/Redis/Docker executables and Ruff/mypy/Twine were unavailable. Accordingly, I did not independently certify PostgreSQL 16/18, real Redis Streams and worker-process behavior, live RLS/grants, migration execution, backup/restore, full compatibility, lint/type checks, dependency vulnerability status, or external deployments.

The wheel contained `py.typed`, Alembic configuration, and all five migration modules. This is a useful packaging observation, but it does not establish that the package installs or runs correctly in every advertised configuration.

### 2.3 Evidence described by the audit but unavailable here

The audit narrative names `results/audit-manifest.json`,
`results/pytest-available.log`, a JUnit XML result, `results/probes.json`,
`reproduce_findings.py`, `source-evidence.md`, `results/artifact-build.json`, and
`results/planning-reconciliation.json`. None of those files, nor the original ZIP,
is present in the supplied workspace. They are therefore **unavailable**, not supplied
evidence, and no current conclusion may depend on resolving or re-hashing them. The
archive digest above is retained as a historical claim from this document and was not
independently recomputed in the current repository.

The authoritative availability manifest is
[`docs/audits/2026-09-07/evidence-status.json`](../docs/audits/2026-09-07/evidence-status.json).
The corrected repository behavior is supported by the ordinary regression and live
integration tests recorded in the current capability ledger, not by the missing probe
bundle.

The diagnostic probes deliberately assert the observed defective behavior so the audit is reproducible. They must be converted into tests asserting the corrected behavior before inclusion in the project's ordinary regression suite. A probe reporting `REPRODUCED` is not a quality pass.

## 3. Architecture assessment

The strongest design choice is the distinction between immutable origin facts, independently retryable destinations, and individual attempts. This is visible in `core/event.py`, `core/delivery.py`, `sqlalchemy/models.py`, and `postgres/leasing.py`. It gives fan-out, retry identity, replay lineage, and operational inspection a coherent model.

The explicit SQLAlchemy UoW binds tenant/subject settings transaction-locally and resets process context in cleanup. Handler execution is separated from the relay's control-plane session. PostgreSQL migrations include role and RLS concerns rather than relying solely on ORM table creation. These are substantive implementations of the plan, even though the individual safety properties still require the live tests and corrections discussed below.

Webhook design makes a serious attempt to own the network boundary: attempt-time DNS validation, explicit-IP connection targeting, original-host SNI/authority, deterministic signed bodies, bounded response parsing, and encrypted signing-secret storage. Its default TLS context enables certificate/hostname verification and TLS 1.2 minimum. The findings concern gaps around this design, not absence of the design.

The source also separates an external executor's acceptance from delivery completion, and command idempotency from a superficial response cache. The reference oracle, deliberate-fault tests, and real infrastructure adapters are valuable assets. The problem is insufficient coverage of several composed failure states, not that the entire test strategy is imaginary.

**Maintainability concern:** the hard part now is the interaction between independently reasonable modules: handoff state versus parent lease state, sink timeouts versus relay lifetime, application permissions versus replay locking, and pre-RC assertions versus final release gates. Tests need to cover these compositions explicitly. Adding more adapters before doing this increases the number of combinations requiring assurance.

## 4. Findings and required remediation

Severity below describes operational or contract impact. A “High” reliability or release-process finding is not automatically a remote security vulnerability. “Reproduced offline” means the real production method was invoked, but no live database or remote receiver was exercised.

### F01 — High: stale Taskiq handoffs can be admitted under a newer delivery lease

**Evidence:** reproduced offline, probe `A01_STALE_TASKIQ_CLAIM`.  
**Code:** `executors/taskiq/store.py:164–211` and `366–394`; `postgres/leasing.py:264–321`.

`claim_execution()` loads a handoff, then combines the current delivery record with the historical attempt referenced by that handoff. It checks whether the current delivery has an unexpired lease. It does not require that this lease token belongs to the historical attempt, or that the referenced attempt is still `started`.

The probe constructed a legitimate post-reclamation shape: attempt A is abandoned, the parent delivery now has attempt B's fresh lease, and handoff A is still enqueued. The real method changed handoff A to `executing`, incremented its execution count, and returned an execution claim even though the old attempt token differed from the current parent token.

A delayed broker message can therefore start old handler work using a newer attempt's lease deadline. Later finalization fencing does not undo side effects already performed. This exceeds the normal documented ambiguity that follows an external effect followed by a crash: stale admission was preventable before the handler began.

**Repair:** make admission verify one coherent parent-delivery/attempt/handoff state under a consistent lock/CAS protocol. Require `delivery.state == leased`, current delivery token equal to the handoff attempt token, referenced attempt still started, and unexpired applicable deadlines. Coordinate recovery and finalization lock ordering. Reject stale work before application session creation or handler execution.

**Acceptance:** a live Redis Streams test delays handoff A, expires/reclaims the parent into B, then delivers both envelopes. A must be a bounded no-op; only B may be admitted. Add simultaneous duplicate messages, expiry while executing, execution-token replacement, and late finalization tests. Reopen the affected M10.04–M10.06 checklist items (`todo.md:1003–1089`).

### F02 — High: expected lease loss can stop the polling relay and cancel unrelated work

**Evidence:** reproduced offline, probe `A02_RELAY_CANCELS_SIBLING`.  
**Code:** `postgres/relay.py:66–157`.

`run_once()` puts claimed deliveries in an `asyncio.TaskGroup`. The sink call is protected by error classification, but `leases.succeed()` and finalization inside `_fail()` can raise outside that protection. A `LeaseLost` exception reaches the task group; sibling tasks are cancelled and `run_once()` raises an exception group. `run()` does not recover from it.

The probe made one delivery lose its lease during finalization while another was executing. The unrelated delivery was cancelled and `LeaseLost` escaped the batch. This is consistent with Python's documented TaskGroup semantics, not an unexpected interpreter behavior.

**Repair:** treat lease loss as a normal per-delivery race, emit a bounded lease-lost observation, and allow unrelated work to continue. Handle retryable database/service outages with explicit bounded operational backoff and supervisor semantics. Preserve cancellation propagation for actual shutdown and avoid suppressing arbitrary programming errors.

**Acceptance:** stale success/failure finalization does not cancel siblings; a transient finalization failure has a documented recovery path; subsequent polling resumes; shutdown still cancels/drains predictably. Reopen M8.15's relay/crash/shutdown guarantees (`todo.md:455–487`).

### F03 — High: attempt duration is not bounded end to end

**Evidence:** timeout-cleanup gap reproduced by `A07_CLOSE_OUTSIDE_TOTAL_TIMEOUT`; DNS/multi-address/redirect/broker gaps established by source inspection.  
**Code:** `webhooks/sink.py:86–189`; `webhooks/transport.py:132–182`; `executors/taskiq/adapter.py:45–73`; `postgres/relay.py:102–157`.

The transport's `total_timeout_seconds` wraps a single connection/exchange, not an entire webhook attempt. Secret retrieval and DNS occur outside that timeout. Each address attempt receives another budget; enabled redirects repeat the process. Additionally, `writer.wait_closed()` is awaited in a `finally` block outside the transport timeout. The Taskiq enqueue path awaits the broker without an adapter-level timeout. The relay itself does not impose a common sink deadline.

The close probe configured a 20 ms total transport timeout and a writer that never completed shutdown. A separate 100 ms watchdog was still needed to cancel the send. This demonstrates the missing code-level bound; it is not a claim that every real asyncio TLS transport hangs indefinitely.

**Impact:** a stuck destination or dependency can occupy a batch, delay shutdown, and outlive its parent lease. Other relays may reclaim the delivery while the first operation remains active.

**Repair:** derive one monotonic attempt deadline from the route budget and remaining lease margin. Apply the remaining budget across keys, DNS, address attempts, redirects, request/response I/O, broker enqueue, and cleanup. Limit address attempts and redirect count; bound shutdown/drain. Define how cancellation and ambiguous broker/network acceptance become durable retry/recovery state.

**Acceptance:** stalled DNS, stalled key provider, many allowed addresses, redirect chains, slow close, and broker stalls all terminate within the declared aggregate budget. The relay remains responsive and unstarted work is not stranded. Reopen the total-duration claims in M9.07 (`todo.md:762–789`).

### F04 — High reliability-contract issue: retry elapsed deadlines are not enforced consistently

**Evidence:** reproduced offline, probes `A03_RETRY_AFTER_DEADLINE` and `A04_RECONCILE_IGNORES_DEADLINE`.  
**Code:** `postgres/leasing.py:61–161`, `223–321`; `core/retry.py:59–85`.

Failure handling asks whether the current time is before the elapsed deadline, then computes a delay without clamping the resulting scheduled time to the remaining budget. The claim query does not reject an already-overdue retry. Expired-lease reconciliation considers the attempt count but ignores maximum elapsed time.

Two examples were reproduced: a failure at elapsed 59 seconds with a 60-second budget produced a retry scheduled for elapsed 69 seconds; a delivery already 120 seconds old with that same budget was returned to `retry_wait` by reconciliation.

**Repair:** give each delivery an unambiguous absolute execution deadline, or derive it consistently from the frozen policy. Enforce it at scheduling, reconciliation, and admission. Decide explicitly whether it is a latest-start or latest-finish bound. Terminalize expired work with a stable reason rather than admitting another attempt. Use a fresh clock reading after external work when applying Retry-After.

**Acceptance:** property/table-driven tests at deadline−epsilon, deadline, and deadline+epsilon; long Retry-After; crash/reconcile after the deadline; delayed backlog; manual replay semantics. No path should silently reinterpret the same frozen policy.

### F05 — High-confidence functional blocker: tenant webhook replay conflicts with application-role grants

**Evidence:** static source finding plus PostgreSQL privilege semantics; live PostgreSQL reproduction is still required.  
**Code:** `webhooks/operations.py:236–253`; `postgres/leasing.py:361–421`; `postgres/migrations/versions/0001_core_runtime.py:49–58`; `postgres/schema.py:46–64`; `postgres/webhook_schema.py:83–100`.

Webhook replay uses the tenant-bound application session and calls `replay_in_transaction()`. That method locks the original delivery with `SELECT ... FOR UPDATE`. The shipped core grants give the application role `SELECT, INSERT` on deliveries, not `UPDATE`; webhook grants do not add it. PostgreSQL requires UPDATE privilege for this row-locking form.

Under the intended application role with the shipped grants and without additional inherited privileges, this path should fail with insufficient privilege. A privileged conformance/operator path would not prove that the public tenant-management path works.

**Repair:** implement a narrow replay operation that preserves immutable history and least privilege. Options include a reviewed security-definer function with fixed search path and explicit tenant/action validation, or a transaction design that does not require a forbidden row lock. Do not fix this by broadly allowing application code to update all delivery-state or snapshot columns. Verify that webhook-management permission cannot replay unrelated destination kinds unintentionally.

**Acceptance:** exercise the actual HTTP/API replay path under the exact unprivileged `mergen_app` role on PostgreSQL 16 and 18. Verify cross-tenant denial, immutable original history, new linked identity, authorization, and a retention/replay race. Reopen the applicable M9.08/M9.11 operational guarantees.

### F06 — High release-process blocker: successful final readiness makes the shared quality gate fail

**Evidence:** reproduced using synthetic readiness data, probe `A08_FINAL_RELEASE_GATE_CONTRADICTION`. No partner/review approval was fabricated or persisted.  
**Code:** `scripts/audit_milestone_thirteen.py:140–160`; `scripts/check.py:47`; `.github/workflows/release.yml:60–69`; `.github/workflows/publish.yml:73–78`; `scripts/audit_release_candidate.py:18–72`.

The Milestone 13 audit asserts that external approval is still incomplete. Once two partners, independent review, RC observation, and a go decision are complete, it raises `Pre-RC repository unexpectedly reports external approval`.

Both release workflows run `scripts/check.py`, which invokes that milestone audit. The final readiness auditor, however, requires those same conditions to be complete. With a synthetic fully ready record and version `1.0.0`, the final readiness auditor passed while the shared milestone audit rejected the record.

**Repair:** separate historical milestone assertions, present implementation checks, RC eligibility, and final promotion. Make the audit explicitly version/phase-aware. Completed approval should not make a healthy implementation check fail. Keep genuine approval requirements fail-closed; do not bypass them to remove the contradiction.

**Acceptance:** a phase table covering current alpha, incomplete RC, ready RC before observation, final release without completed observation, and fully ready final release. Exercise the actual shared workflow command chain. This is a blocker for v1 publication, not a reason to claim the current alpha should already have external approval.

### F07 — Medium security/configuration issue: production mode accepts an insecure supplied TLS context

**Evidence:** reproduced offline, probe `A06_UNSAFE_PRODUCTION_TLS_CONFIG`.  
**Code:** `webhooks/transport.py:97–108`, `133–140`, `211–216`.

The default SSL context is appropriately configured. However, a caller-supplied context is accepted in production mode without checking certificate verification, hostname checking, or the minimum protocol setting. A context with `CERT_NONE` and `check_hostname=False` reached the connection opener in the probe.

This is an unsafe configuration path, not a default unauthenticated TLS connection and not a demonstrated remote SSRF bypass.

**Repair:** production mode must validate the supplied context or construct the security policy itself while accepting only trusted CA configuration. Keep intentionally insecure fixtures behind an explicit test/nonproduction boundary. Ensure a mutable context cannot later silently weaken the guarantee.

**Acceptance:** fail before I/O for verification disabled, hostname checking disabled, or policy below the supported TLS minimum. A custom trusted CA with hostname verification enabled must still work. This contradicts the unconditional production TLS assertion in M9.06 (`todo.md:754–760`).

### F08 — Medium: informational HTTP responses are mistaken for final delivery outcomes

**Evidence:** reproduced offline, probe `A05_INTERIM_HTTP_MISCLASSIFIED`.  
**Code:** `webhooks/http11.py:47–102`; `webhooks/classification.py:25–52`.

The parser returns after a single response status/header section. A stream containing `103 Early Hints` followed by a valid `204 No Content` was returned as status 103; the final 204 remained unread and classification marked the delivery permanently failed.

HTTP permits informational responses before the final response and requires clients to parse them. Sending no `Expect` header does not justify assuming none can arrive.

**Repair:** consume informational responses until a final response arrives, while sharing aggregate time/header/count budgets. Treat unsupported protocol upgrade explicitly rather than accidentally accepting it.

**Acceptance:** 100→204, 103→200/204, multiple informational responses, excessive interim responses, premature EOF, and upgrade handling. Maintain the existing body-discard and byte-limit guarantees.

### F09 — Medium structural risk; v1 blocker: historical migrations depend on mutable runtime definitions

**Evidence:** source inspection; no historical migration failure or data loss independently reproduced.  
**Code:** `postgres/migrations/versions/0001_core_runtime.py:12–17,36–48,65–70`; `0002_webhooks.py:13–15,31–40`; subsequent revision imports; `tests/migrations/test_revision_matrix.py:25–64`.

Historical revisions import current ORM table collections and current RLS/grant helpers. Future changes to a runtime model or helper can therefore change what an old migration means without changing that migration file. A matrix that runs older revision labels using only today's source tree does not, by itself, reproduce the schema created by a previously published wheel.

**Repair:** freeze revision-local table definitions and security SQL, or use explicitly immutable, versioned migration helpers. Inventory which schema-bearing artifacts were actually published rather than treating all planned alpha versions as released history. Keep forward evolution additive and test preserved data, ownership, grants, RLS, constraints, and indexes.

**Acceptance:** create databases from retained historical release artifacts where those artifacts exist, seed representative histories, then upgrade using the candidate wheel. Also test unsupported/downgrade behavior explicitly. This is preventive migration discipline, not evidence that the existing five migrations have already corrupted data.

### F10 — Medium assurance/planning issue: completion claims are broader than demonstrated evidence

**Evidence:** supplied plan/checklist plus executable gates.  
**Code/documents:** `scripts/check_documentation.py:14–34`; `scripts/audit_milestone_thirteen.py`; `plan.md:3–18,60–74,543–561`; `todo.md:1650–1682,1837–1864`.

The supplied plan is still written from an assurance-only baseline. The checklist is much newer in substance, but uses binary checked items for implementation, local checks, hosted verification, external validation, and release status. Its “every documented command and code sample is executed in CI” assertion is broader than the documentation smoke script, which compiles example files and executes three CLI commands. Other CI tests may cover individual examples, but that is not evidence of exhaustive Markdown-snippet execution.

The local M13 audit passed in this environment even though the eight new diagnostic probes reproduced defects. That does not make the audit useless: it demonstrates why scaffolding, file existence, and historical result checks must not be mistaken for live correctness tests. The repository already explicitly marks historical compatibility JSON as non-release-authoritative; preserve that distinction rather than discarding the useful evidence framework.

**Repair:** assign each capability a state such as `IMPLEMENTED`, `LOCAL_VERIFIED`, `HOSTED_VERIFIED`, `EXTERNALLY_VALIDATED`, or `RELEASED`, with applicability, command, source/artifact identity, infrastructure, result, owner, and timestamp. Reopen specific DoD items contradicted by findings. Execute a maintained inventory of documentation scenarios, or narrow the exhaustive claim.

## 5. Milestone reconciliation

| Milestone | What the supplied archive supports | Recommended current classification |
|---|---|---|
| M8 core runtime | Real UoW, persistence, roles/RLS, leases, relay, handler executor, and runtime adapter exist | Implemented; reopen liveness/deadline/admission-related verification |
| M9 webhooks | Subscriptions, encrypted secrets, signing, explicit-IP transport, operations, and adapter exist | Implemented beta surface; timeout, TLS, interim response, and app-role replay blockers |
| M10 Taskiq | Durable handoffs and worker bridge exist | Experimental alpha; stale-admission fix and real delayed-message verification required |
| M11 command idempotency | Transaction-owned ledger, fingerprinting, safe replay, operations, and tests exist | Implemented alpha; live concurrent-request certification not independently rerun here |
| M12 delegation/FastMCP | Issuance, verification, key lifecycle, downstream enforcement, and bridge exist | Implemented alpha; full installed integration matrix not independently rerun here |
| M13 hardening | Considerable migration, benchmark, restore, documentation, evidence, and workflow infrastructure exists | In progress, not merely waiting for external sign-off; repair release contradiction and assurance gaps |

A task heading marked checked is not the same thing as a released milestone. The checklist currently marks 56 of 64 task headings complete; release/partner gates remain open. That arithmetic is descriptive, not a completion percentage for the product.

## 6. Audit of the supplied plan

### 6.1 Preserve the product definition, replace the starting point

The plan's definition—transaction boundary for tenant-safe side effects—is still suitable. The declared non-goals are particularly useful: no workflow engine, generic queue, user-management product, hosted dashboard, non-PostgreSQL store, or generic exactly-once claim through v1.

Its executive baseline and immediate sequence are obsolete. Do not restart M8 from placeholders, recreate historical branches, or rewrite Git history to make the old chronology look complete. Archive the August 27 plan as historical and write a current baseline for the `0.11.0a1` source actually being maintained.

### 6.2 Separate feature existence from its support promise

The plan intended the webhook MDP to lead adoption, with optional work gated by demand. The archive already contains all optional work while the readiness record still has no partner deployments. Existing work need not be deleted, but it should not force all optional integrations into the initial stable support contract.

Prioritize supported core runtime, tenant isolation, reliable in-process handling, and webhook delivery. Keep Taskiq and delegation explicitly experimental until their own correctness and adoption gates are met. Promote command idempotency when a partner needs it and its real HTTP/transaction scenarios pass. Internal dogfooding is useful but does not substitute for the plan's independent partner requirement.

### 6.3 Reconcile effort estimates rather than carrying them forward

The plan's original engineering estimate is **395–570 hours**, excluding external time. Adding the individual task estimates in the supplied TODO gives **445–655 hours**. These are historical scope estimates, not remaining work or measured effort.

| Milestone | Plan estimate | Sum of detailed TODO estimates |
|---|---:|---:|
| M8 | 100–145 h | 135–198 h |
| M9 | 75–105 h | 87–128 h |
| M10 | 40–60 h | 40–60 h |
| M11 | 45–65 h | 52–75 h |
| M12 | 45–65 h | 46–69 h |
| M13 | 90–130 h | 85–125 h |
| **Total** | **395–570 h** | **445–655 h** |

M8 is the largest mismatch. The right correction is not to add either entire estimate to the current schedule. Re-estimate only open defects, verification, adoption work, and promotion tasks against the present code. Keep independent review and deployment observation outside engineering-hour totals.

### 6.4 Do not move package versions backwards

The package is already `0.11.0a1`. The old `0.8.0b1` webhook target can remain a historical milestone label, but the next actual distribution should advance from the present version. A compatible repair alpha could be `0.11.0a2`; a changed pre-v1 API/schema contract may justify a new alpha line. Choose the first beta version after scope and compatibility decisions, not because the old M9 table contains a beta number.

## 7. Recommended roadmap from the current snapshot

The critical path should become:

**Rebaseline → repair reliability/security boundaries → certify the exact candidate on real infrastructure → ship a narrow beta → collect independent deployment/review evidence → observe RC → approve v1.**

The following budgets are planning allowances for newly identified and remaining engineering work, not a verified forecast. They assume the source can be reproduced in the intended locked environment and will need revision after the first live verification pass.

| Phase | Focus | Engineering allowance | Exit condition |
|---|---|---:|---|
| R0 | Truthful baseline and evidence ledger | 4–8 h | Current plan/status, finding owners, reopened DoD items, exact source identity |
| R1 | Correctness and boundary repairs | 40–70 h | F01–F05, F07–F08 fixed; regression tests assert safe behavior |
| R2 | Real verification and reproducible release machinery | 30–50 h | PG16/18 + selected real adapters, frozen migration definitions, F06 fixed, clean candidate artifacts |
| R3 | Core/webhook beta and first partner | 16–30 h + partner time | One independent serious staging deployment completes the full lifecycle and records actionable feedback |
| R4 | Independent review and second deployment | 20–40 h + external time | No unresolved high/critical or contract-breaking issues; two serious deployments; restore/operations demonstrated |
| R5 | RC observation and v1 decision | 8–16 h + observation | Exact RC observed, no reset/blockers, complete evidence and explicit approval |
| **Total allowance** | | **118–214 h + external time** | Re-estimate after R2 |

At the plan's stated ten engineering hours per week, the allowance corresponds to approximately **12–22 capacity weeks**, before independent waiting/observation time. This is not a promised calendar completion date. Work on a new adapter or workflow layer is excluded.

### R0 — Rebaseline without rewriting history

Keep the original baseline provenance in historical documentation. Update the live plan to the present alpha and maintain a capability/evidence ledger. Record this audit as unresolved findings with severity, owner, target, regression test, resolution, and disclosure status. Make the meaning of “implemented,” “verified,” and “released” explicit.

### R1 — Repair the composed state machines first

Start with stale Taskiq admission, then per-delivery relay isolation, common attempt budgets, and retry-deadline enforcement. Repair application-role replay without widening runtime grants. Add TLS context validation and informational-response parsing. These fixes should arrive with regression tests and documentation in the same logical branches.

The important acceptance criterion is behavior under recovery and contention, not successful happy-path delivery. Do not waive a failed stale-worker test because finalization later rejects the worker: handler-side effects may already have occurred.

### R2 — Verify the actual implementation and artifact

Recreate the declared dependency environment. Run Ruff, strict mypy, the non-integration suite, packaging, and selected documentation scenarios. Provision real PostgreSQL 16 and 18 with the exact runtime roles. Add the new concurrency, deadline, and replay tests to the real adapters or their integration suites. Run Taskiq against Redis Streams with a separately started worker when claiming executor support.

Freeze migration-local schema/security definitions and compare upgrades from retained actual historical artifacts. Run the whole shared release command chain through alpha/RC/final readiness fixtures. Build wheel and sdist from the verified source and then exercise those artifacts in clean environments, including supported extras. Bind each report to the candidate commit, artifact hash, lockfile, database, driver, schema, and adapter configuration.

### R3 — Ship a deliberately narrow beta

The supported user journey should be one coherent vertical slice: authenticated tenant request → business transaction and effect intent → handler/webhook delivery → failure → retry → success → authorized manual replay → retention/restore inspection.

Make the beta installable and understandable without requiring Taskiq, FastMCP, or an observability backend. Keep those optional features experimental unless the partner actually exercises them. Record setup friction and every operational intervention. A partner merely running unit tests is not equivalent to a serious staging deployment.

### R4 — Earn the production support contract

Obtain independent review of the RLS/grants boundary, hostile webhook transport, secret lifecycle, delegation target/authority checks, and evidence handling. The supplied internal findings register is not an independent review. Exercise migration, backup/restore, key rotation, replay, dead-letter recovery, and incident procedures in two serious external environments. Record managed-service failover as unverified unless it is actually exercised; retain the repository's existing distinction between local restart and managed failover.

### R5 — Promote the observed candidate, not a different build

Set the RC's API/schema/support scope, publish its evidence, and observe that exact candidate under the approved protocol. Define the observation start/end, workload, failure coverage, reset conditions, and approval requirements explicitly. A contract-changing fix resets the relevant observation decision. Only then publish v1 from the protected workflow with the required artifacts, provenance, and approvals.

## 8. Regression and verification matrix to add

| Boundary | Required scenario | Minimum test level |
|---|---|---|
| Taskiq admission | Old handoff delivered after parent reclaim | Unit probe converted to safe assertion + live PG/Redis worker |
| Taskiq duplicate execution | Concurrent duplicate messages before and after execution expiry | Live separate-worker test |
| Relay finalization | LeaseLost on one delivery while sibling runs | Unit + PG concurrency |
| Relay operational recovery | DB unavailable during claim/finalization, then restored | Controlled service failure |
| Aggregate attempt deadline | DNS/key/broker stall, multiple addresses, redirects, slow close | Deterministic fixtures + live transport rehearsal |
| Retry lifecycle | Scheduling and reconciliation at/after elapsed deadline | Clock-injected tests + PG persistence |
| Tenant replay | Actual endpoint using exact application grants | Live PG16/18 + ASGI request |
| Replay/retention | Terminal row replayed while retention considers it | Concurrent PG test |
| TLS configuration | Disabled verification rejected; trusted custom CA accepted | Unit + local TLS |
| HTTP parsing | Informational responses before final 2xx; bounded interim flood | Byte-level parser tests |
| Migration history | Old actual artifact database upgraded by candidate wheel | Artifact-driven migration matrix |
| Release phases | Incomplete alpha, eligible RC, ineligible final, eligible final | Shared-script/workflow contract tests |
| Documentation | Enumerated install/quickstart/operations scenarios | Installed-wheel documentation smoke suite |
| Tenant authority | Cross-tenant denial under real roles; relay never used by handler | Live permission/session tests |
| Command idempotency | Concurrent identical HTTP requests and rollback/expiry conflicts | Real ASGI + PG transaction tests |
| Delegation | Real installed bridge, target mismatch, scope attenuation, no token forwarding | Supported FastMCP version + downstream ASGI |

Avoid overstating what any single level proves. A model test can establish a predicate defect; a live test establishes actual database/broker interaction; external deployment evidence addresses operation and usability beyond the repository.

## 9. Product and post-v1 priorities

The next development objective should be a trustworthy, usable transaction/effect boundary, not breadth. Measure committed-intent preservation under the defined crash matrix, delivery latency/backlog age, lease loss, retries/dead letters, fairness, restore integrity, secret/credential leakage, and partner operational burden. Set numeric SLOs from reproducible workloads and partner requirements; this audit did not measure deployment throughput and does not propose invented performance claims.

Prioritize simpler installation, permission diagnostics, actionable error messages, coherent runbooks, and repeatable recovery before another integration. Keep one distribution and extras. Do not add workflow orchestration, broad task-queue semantics, non-PostgreSQL persistence, synchronous SQLAlchemy, a hosted control plane, or more executor adapters merely to enlarge the feature list.

The plan's demand gates remain useful: let external use decide which optional capability becomes supported. If practitioners consistently value conformance and diagnostics more than the embedded runtime, preserve the planned option to emphasize the assurance suite rather than growing an unadopted runtime indefinitely.

## 10. Final recommendation

**Continue. Do not rewrite. Do not promote on the current evidence.**

FastAPI-Mergen has crossed the important threshold from assurance scaffolding to a substantive implementation. Its immediate challenge is making the composed runtime and release states match the guarantees already written in the checklist. The best next milestone is a repaired, reproducibly verified core/webhook beta with a real external user—not another feature milestone and not v1 by checklist arithmetic.

## References and evidence provenance

The primary materials currently present are this audit plus `plan.md`, `todo.md`, and
`remediation.md`. The original archive and the evidence bundle described in section 2.3
are unavailable, so the archive/source-excerpt claims cannot be independently resolved
from this workspace. File line references refer to the supplied snapshots, not an
assumed hosted repository revision. Current repair evidence is recorded separately in
the capability ledger and ordinary repository tests.

External references used only to verify platform semantics:

1. Python documentation, **Coroutines and tasks — Task groups**: `https://docs.python.org/3/library/asyncio-task.html`.
2. PostgreSQL 18 documentation, **SELECT — privileges and row-locking clauses**: `https://www.postgresql.org/docs/current/sql-select.html`.
3. RFC 9110, **HTTP Semantics, §15.2 Informational 1xx**: `https://www.rfc-editor.org/rfc/rfc9110`.

The audit does not claim current hosted CI results, a dependency-CVE clearance, live infrastructure certification, or independent partner/security approval. Those remain explicit verification tasks.

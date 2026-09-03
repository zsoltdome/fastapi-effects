# FastAPI-Mergen — Remediation and release TODO

**Date:** 7 September 2026  
**Baseline:** supplied archive SHA-256 `14db08002daa8771699d03b925dbccba46e5a39857db4a637818ebb2e3039fb0`, package version `0.11.0a1`, corresponding to repository commit `d1ecc7f334c5269afaa11703fdfd94363a27f9d6`.  
**Companion:** [`audit_road.md`](audit_road.md). The source planning files in this workspace are [`plan.md`](plan.md) and [`todo.md`](todo.md); the audit's `plan(8).md` and `todo(8).md` names record their supplied names.  
**Policy:** do not check a task until its stated acceptance evidence exists. These tasks supersede the old plan's immediate restoration sequence, not the historical record of M8–M13.

Findings F01–F10 come from the companion audit. F11 was found while validating this remediation plan against the actual release-gate implementation. F12 was found while exercising F05 through the real FastAPI router: postponed local dependency annotations were interpreted as request fields, so the public router returned `422` before dependency injection. F13 was found by running the shared quality gate: Git governance rejected the explicitly preserved recovery-baseline commit because its historical email and one-word subject predate the current rule. F14 was found by exercising the complete artifact path: `scripts/check.py` passed `dist/.gitignore` to Twine and therefore made every otherwise-successful local release check fail at its last step. F15 was found during final remediation review: the new address-attempt cap truncated DNS answers before validating the complete set, contradicting the fail-closed mixed-address policy. F16 was found during the commit-readiness review: the shared check hard-coded the pre-v1 phase, which would reject a populated RC record before the tagged workflow could run its automatic RC gate. F17 was found in the same review: a matching token could still finalize after lease expiry when reconciliation had not yet run, and success finalization did not independently fence the handler/delivery deadline. F18 was found while reviewing evidence validation: references were checked for existence without being constrained to repository-contained paths.

## Current execution status

The committed local-verification source implements F01–F18 and has local regression evidence. The full integration selection passes on PostgreSQL 16 and PostgreSQL 18 with the exact generated runtime roles; Ruff and mypy pass. The stale/current Taskiq case runs through Redis Streams and a separately started CLI worker, the historical-artifact inventory records an evidence-backed `NOT_APPLICABLE`, and all 40 executable-language Markdown blocks are content-bound in the maintained documentation inventory. Clean wheel/sdist installs across the supported extras and Twine validation also pass locally. These are not yet candidate-bound, hosted, or external results. Exact-candidate documentation journeys, hosted security/provenance, partner deployments, independent review, and RC observation remain open. See the tracked `docs/planning/current-remediation.md`, capability ledger, and findings register for the evidence-stage distinction.

## Status vocabulary

Use `OPEN → IMPLEMENTED → LOCAL_VERIFIED → HOSTED_VERIFIED → EXTERNALLY_VALIDATED → RELEASED`, recording `NOT_APPLICABLE` with a reason where a stage genuinely does not apply. The task checkboxes below mean only that the complete acceptance paragraph is satisfied; they are not the capability status ledger. Store the tracked capability ledger at `docs/planning/capability-evidence-ledger.md` with a machine-readable companion at `docs/planning/capability-evidence-ledger.json`. Each entry records an owner, applicable stages, evidence command, source commit, artifact digest, infrastructure and dependency versions, result, evidence location, and timestamp. Do not infer release readiness from a count of checked boxes.

## R0 — Establish the present baseline

### - [x] R0.1 — Update the live plan and capability ledger

**Finding:** F10. **Depends on:** none. **Suggested branch:** `docs/rebaseline-runtime-readiness`.

Replace the assurance-only opening in `docs/planning/product-engineering-plan.md` with the actual `0.11.0a1` runtime inventory. Preserve the unavailable-M2–M6 provenance statement in historical documentation. Distinguish package version from capability maturity and schema revision. Retain the current alpha label.

**Acceptance:** `README.md`, `docs/planning/product-engineering-plan.md`, `CHANGELOG.md`, the public API/support table, and the tracked current TODO agree. Old M8–M13 headings remain historical; no artificial backdated releases or fabricated Git history are introduced. The capability ledger exists at the paths above and lists pending live checks and external gates explicitly.

### - [x] R0.2 — Register findings and reopen affected guarantees

**Findings:** F01–F18. **Depends on:** R0.1.

Enter findings in `docs/security-review/findings.md` with severity, owner, affected version, regression test, target, resolution, and disclosure status. Reopen the relevant M8.15, M9.06–M9.08, M10.04–M10.06, M13.02/M13.09, and release-gate assertions as needed; do not mark an entire milestone nonexistent because part of its DoD is contradicted.

**Acceptance:** every finding has an explicit disposition. The audit's mock-backed probes are labelled diagnostic reproductions, not real-runtime certification.

### - [x] R0.3 — Restore audit evidence and make references resolvable

**Finding:** F10/evidence-integrity follow-up. **Depends on:** none. **Suggested branch:** `docs/preserve-audit-evidence`.

Recover the audit manifest, probe source/results, pytest log and JUnit output, source excerpts, artifact-build record, and planning reconciliation named in `audit_road.md`. Store immutable, non-sensitive evidence in a tracked `docs/audits/2026-09-07/` bundle. If an item cannot be recovered, change the audit to state that it is unavailable and downgrade any evidence classification that depends on it. Use repository-relative source paths, and retain a short mapping for any supplied filenames that differ from their repository names. The four supplied governing documents now have explicit Git-trackable exceptions under `sup/`; unrelated `sup/` scratch material remains ignored.

**Acceptance:** every claimed supplied evidence file resolves and is bound to the archive hash and commit, or the audit explicitly identifies it as unavailable. All local document and source references resolve from the tracked audit location. `git check-ignore` does not classify the governing copies as ignored.

## R1 — Repair runtime and transport boundaries

### - [x] R1.1 — Fence Taskiq admission against the current parent attempt

**Finding:** F01. **Depends on:** R0.2. **Suggested branch:** `fix/fence-taskiq-attempt-admission`.

Lock or compare-and-set the handoff, referenced attempt, and parent delivery as a coherent state. Require a leased parent, matching current lease token, started referenced attempt, and unexpired applicable deadlines. Apply one consistent lock order across admission, recovery, and finalization. Reject stale envelopes before any handler execution or application session creation.

**Acceptance:** convert probe A01 into a test requiring a no-op/rejection. A live Redis Streams worker test delivers an old handoff after parent reclamation and observes zero handler admissions for that stale handoff. Concurrent duplicates, execution expiry, token replacement, and stale finalization also pass.

### - [x] R1.2 — Isolate lease loss within one delivery

**Finding:** F02. **Depends on:** R0.2. **Suggested branch:** `fix/isolate-relay-lease-loss`.

Contain expected `LeaseLost` outcomes from success and failure finalization. Emit bounded metadata; allow sibling deliveries and future polling to continue. Specify which database/service failures retry operationally and which programming errors escalate. Preserve true shutdown cancellation.

**Acceptance:** converted probe A02 requires the unrelated sibling to finish and the relay to continue polling. Tests cover success-finalization lease loss, failure-finalization lease loss, a transient database interruption, and orderly shutdown.

### - [x] R1.3 — Enforce one aggregate attempt budget

**Finding:** F03. **Depends on:** R0.2. Coordinate deadline semantics with R1.4. **Suggested branch:** `fix/bound-delivery-attempt-lifetime`.

Derive a monotonic total deadline from route policy and remaining lease time. Carry remaining budget through key lookup, DNS, address attempts, redirects, request/response I/O, broker enqueue, and cleanup. Bound address/redirect counts and cancellation/drain behavior. Describe ambiguous acceptance and recovery rather than claiming that timeout proves non-delivery.

**Acceptance:** converted probe A07 terminates inside the configured aggregate bound without an extra watchdog. Deterministic fixtures cover stalled DNS/key provider, many addresses, redirect chains, slow close, and broker stalls. A live rehearsal verifies that the next polling cycle and shutdown remain responsive.

### - [x] R1.4 — Enforce elapsed retry deadlines at every transition

**Finding:** F04. **Depends on:** R0.2. Coordinate deadline semantics with R1.3. **Suggested branch:** `fix/enforce-delivery-retry-deadlines`.

Define whether the policy is latest-start or latest-finish. Use one absolute deadline or one consistent derivation. Enforce it in fail/schedule, expired-lease reconciliation, and claim/admission. Use a current post-I/O clock reading for Retry-After. Define replay's new budget without changing the original delivery.

**Acceptance:** converted probes A03/A04 no longer schedule or admit expired work. Tests exercise just-before, exactly-at, and just-after deadlines, maximum Retry-After, delayed backlog, crashes, and replay.

### - [x] R1.5 — Repair tenant replay without widening application authority

**Findings:** F05 and F12. **Depends on:** R0.2. Coordinate replay-budget semantics with R1.4. **Suggested branch:** `fix/restore-least-privilege-replay`.

First reproduce the exact `mergen_app` privilege failure on PostgreSQL 16 and 18. Replace the unsupported row-locking path with a least-privilege operation, such as a reviewed tenant-validating function or an alternative safe transaction design. Do not broadly grant application UPDATE over delivery-state/snapshot columns. Check destination-kind restrictions for webhook-only management authority. Exercise the actual FastAPI router so closure-scoped `Depends` annotations are resolved as dependencies rather than exposed as query parameters.

**Acceptance:** the public replay endpoint succeeds under the intended app role, creates a new linked identity, and preserves terminal history. Cross-tenant and unauthorized replay fail. Concurrent retention/replay behavior is defined and tested. A migration applies any new function/grant safely.

### - [x] R1.6 — Validate production TLS contexts

**Finding:** F07. **Depends on:** R1.3. **Suggested branch:** `fix/validate-production-tls-policy`.

Reject supplied contexts that disable certificate or hostname verification or fall below the declared protocol minimum. Support custom trusted CA material without accepting an unrestricted security downgrade. Keep insecure test fixtures explicitly nonproduction.

**Acceptance:** converted probe A06 rejects before I/O. Positive local-TLS tests verify custom-CA hostname validation and original-host SNI while connecting to the approved explicit IP. Test context mutation or avoid sharing mutable security configuration.

### - [x] R1.7 — Consume informational HTTP responses correctly

**Finding:** F08. **Depends on:** R1.3. **Suggested branch:** `fix/parse-final-webhook-responses`.

Parse zero or more informational responses before the final response. Share aggregate count/header/time budgets. Handle unsupported upgrades explicitly.

**Acceptance:** converted probe A05 returns the final 204 and success. Test 100→204, 103→200, several informational responses, excessive interim responses, EOF, and protocol upgrade, while preserving body-discard and secret-minimization tests.

## R2 — Reproduce infrastructure and release evidence

### - [x] R2.1 — Make release auditing phase-aware

**Findings:** F06, F11, F13, and F14. **Depends on:** R0.2. **Suggested branch:** `fix/separate-release-readiness-phases`.

Remove the contradiction between an assertion that external approval must still be absent and a final gate requiring that approval. Separate historical milestone validation from current implementation health and RC/final readiness. Validate the complete readiness-record schema rather than counting truthy placeholders: require two distinct partner IDs and independent environment owners, permitted non-demo deployment classes, the mandatory exercise/capability set, bounded evidence IDs, unique SHA-256 evidence digests, both approvals, an independent-review digest and disposition, a valid observation interval, candidate/artifact identity, a go decision, and two distinct approvers. Retain fail-closed partner, review, observation, and approval checks. Make Git-governance checks compatible with the documented immutable recovery baseline without waiving the rules for later commits.

**Acceptance:** convert A08 into a phase-table test. Alpha/incomplete RC/ready RC/unobserved final/ready final have the correct outcomes through the actual `scripts/check.py` and release-workflow command chain. Negative tests reject missing partner fields, demo deployments, missing exercises, malformed or duplicate digests, duplicate partner/owner/approver identities, unresolved issues, missing review evidence, invalid observation dates, and candidate/artifact mismatches. Synthetic fixture approvals are never written as real production evidence.

### - [x] R2.2 — Freeze revision-local schema and security definitions

**Finding:** F09. **Depends on:** R1.5. **Suggested branch:** `fix/freeze-historical-migration-definitions`.

Replace dependencies on mutable ORM table collections and current security helpers with frozen revision-local or explicitly immutable versioned definitions. Inventory actual published schema-bearing artifacts separately from planned versions.

**Acceptance:** a runtime-model or current-helper change does not alter old migration output. Inventory the release index/PyPI and retained artifacts first. Where a published schema-bearing artifact exists, create and seed its database and upgrade it with the candidate wheel while verifying protected data and grants/RLS/constraints/indexes. Where none exists, record `NOT_APPLICABLE` with the inventory evidence and test upgrades across every revision shipped in the candidate. Unsupported downgrades fail with documented instructions.

### - [ ] R2.3 — Run the locked live verification matrix

**Findings:** F01–F05, F07–F09, and F12. **Depends on:** R1.1–R1.7 and R2.2. **Suggested branch:** `test/certify-repaired-runtime-boundaries`.

Recreate the declared dependency environment. Run quality checks, real PostgreSQL 16/18 suites with exact app/relay/migration roles, and all supported-capability adapters. Exercise Taskiq via Redis Streams and a separate worker process, not only direct method calls. Test the public tenant management path separately from privileged operator/conformance paths.

**Acceptance:** evidence contains no unreported skipped infrastructure checks. Reports identify source commit, package version, lock digest, DB/driver/schema versions, adapter configuration, command, and result. The new composed-state tests run in CI and fail when the original defects are reintroduced.

### - [ ] R2.4 — Execute documentation scenarios and certify clean artifacts

**Findings:** F10 and F14. **Depends on:** R2.1–R2.3. **Suggested branch:** `test/verify-installed-user-journeys`.

Create an explicit inventory of supported documentation commands/scenarios. Execute install, quickstart, relay, webhook lifecycle, replay, and selected optional integrations from the built wheel. Keep syntax compilation distinct from execution. Build wheel/sdist, run Twine, base/extra clean installations, and extracted-archive behavior. Verify Git governance in the actual repository or governed release artifact.

**Acceptance:** no “all snippets executed” claim without an exhaustive maintained inventory. Results bind to exact wheel/sdist hashes, not just a nearby source checkout. Publish only artifacts produced by the protected verified workflow.

## R3 — First externally validated beta

### - [ ] R3.1 — Freeze a narrow supported beta surface

**Depends on:** R2.1–R2.4. **Suggested branch:** `docs/define-supported-beta-capabilities`.

Prioritize core transaction/effect semantics, in-process handlers, tenant isolation, and webhooks. Retain Taskiq/delegation as experimental unless their specific verification and use-case gates are met. Choose the next increasing package version from the existing `0.11.0a1` line; do not publish a retrograde `0.8` version to match the historical plan.

**Acceptance:** support table names precisely what is stable, experimental, reference-only, unsupported, or not yet verified. One installation/tutorial path succeeds without unnecessary optional frameworks.

### - [ ] R3.2 — Complete the first independent live deployment

**Depends on:** R3.1. **External gate.**

A design partner runs the exact candidate in a non-demo live staging or production-like environment through request→atomic intent→failure→retry→success→replay, plus diagnostics, migration, retention, restore, and an incident exercise. Record environment ownership, workload realism, setup friction, incidents, manual interventions, and prioritized feedback with dispositions. A production-like substitute for production must meet documented equivalence criteria for data scale, traffic, managed dependencies, failure injection, operational ownership, and observation duration.

**Acceptance:** partner-approved evidence exists from a serious independent environment and satisfies the complete readiness-record schema enforced by R2.1. Internal dogfooding, a demo, or a successful unit-test run does not satisfy this gate.

## R4 — Production support evidence

### - [ ] R4.1 — Complete independent review and supply-chain gates

**Depends on:** R2.1–R2.4 and R3.1. **External/hosted gate.**

Review RLS/grants, stale-worker handling, hostile webhook transport, secret/key lifecycle, command replay safety, delegation target/authority boundaries, and evidence redaction. Execute current dependency/security/license checks in the supported environment. Generate SBOM and release provenance through the intended protected process.

**Acceptance:** independent findings have owners/dispositions; no unresolved high/critical or contract-breaking issue remains. Historical internal findings are not relabelled independent review. Attach evidence to the exact candidate artifact.

### - [ ] R4.2 — Complete the second independent live deployment

**Depends on:** R3.2, R4.1. **External gate.**

Use a partner and environment owner distinct from R3.2. Exercise workload-specific latency/backlog/fairness and failure recovery, restore preserved identities, rehearse key rotation and incidents, and record operational limits. This must be an external production deployment or satisfy the same documented production-equivalence criteria as R3.2. Do not equate a local single-node restart with managed-service failover.

**Acceptance:** two distinct complete partner records and applicable real profiles are recorded; both are non-demo live deployments, or any production-like substitute has an approved equivalence record. Workload and operational evidence are reproducible and all blocking feedback is resolved.

## R5 — RC and v1

### - [ ] R5.1 — Observe an immutable release candidate

**Depends on:** R4 complete and phase-aware hosted gates. **Engineering plus observation gate.**

Freeze the RC API/schema/support promise. Define observation duration and workload, start/end records, failure scenarios, triage criteria, reset conditions, and required approvals. Observe the exact built candidate, not an untracked working tree.

**Acceptance:** observation completes without unresolved blockers. A contract-changing fix triggers the defined reset. All candidate evidence is published and bound to source/artifact identity.

### - [ ] R5.2 — Approve and publish v1 from the verified artifacts

**Depends on:** R5.1. **Protected release gate.**

Run final readiness with two distinct approvers, completed independent review/partners/observation, compatible migrations, complete selected-capability profiles, and required artifacts/provenance. Perform trusted publication and verify installed artifacts.

**Acceptance:** the release is reproducible, phase gates have consistent outcomes, and the post-v1 backlog remains demand-ranked. No workflow engine, new storage backend, synchronous API, extra distribution, or new adapter is admitted without a demonstrated requirement and explicit scope decision.

## Scheduling and sequencing

The companion report's **118–214 engineering-hour planning allowance plus external time** predates F11 and the evidence-integrity work in R0.3. Treat it as historical input, not the current forecast. Re-estimate after the shared deadline/replay decisions and the first locked live verification pass; keep independent review, deployment, and observation waiting outside engineering-hour totals.

R1.1, R1.2, R1.3, R1.4, and R1.5 can proceed independently after agreeing the shared attempt/deadline and replay-budget semantics; R1.6/R1.7 should land with the aggregate transport-budget work. Release-phase repair can run in parallel with runtime fixes. For solo development, keep concurrency low and finish behavior, regression evidence, and documentation together rather than leaving many partly repaired branches.

The next product milestone is a repaired, externally exercised core/webhook beta. Additional feature breadth is not on the critical path.

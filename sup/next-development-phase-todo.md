# FastAPI-Mergen — Next development phase TODO

**Prepared:** 8 September 2026  
**Starting line:** pushed `main` after remediation findings F01–F18  
**Package baseline:** `0.11.0a1`  
**Target phase:** exact-candidate alpha verification and beta-surface freeze  
**Primary roadmap items:** R2.3, R2.4, then R3.1 from [`remediation.md`](remediation.md)

## Phase objective

Turn the locally verified remediation tree into a reproducible, hosted, artifact-bound
candidate. Exercise every supported runtime journey from the built distributions, close
the remaining engineering evidence gaps, and freeze a narrow beta support surface. This
phase does not claim partner validation, independent review, RC observation, or v1
approval; those remain later external gates.

The default next package version is `0.11.0a2` because the work repairs the existing
alpha line. Change that choice only if compatibility review identifies an intentional
pre-v1 API or schema break.

## Operating rules

- [ ] Work from a clean branch created from the pushed remediation head.
- [ ] Keep `OPEN → IMPLEMENTED → LOCAL_VERIFIED → HOSTED_VERIFIED →
  EXTERNALLY_VALIDATED → RELEASED` as the evidence vocabulary.
- [ ] Never promote a capability because an adjacent capability passed.
- [ ] Treat source commit, lock digest, wheel digest, and sdist digest as one candidate
  identity; invalidate evidence after any source or dependency change.
- [ ] Build release distributions once in the protected workflow and reuse those exact
  files for every artifact-bound test and publication step.
- [ ] Record skipped infrastructure checks as blockers; do not silently convert them to
  passes or `NOT_APPLICABLE`.
- [ ] Keep partner names, credentials, URLs, tokens, payloads, and raw incident data out
  of public evidence.
- [ ] Do not create a release tag or publish to an index until all phase exit criteria
  and the applicable release-readiness gate pass.

## Workstream A — Freeze the candidate identity

### A1. Select and declare the candidate

- [ ] Confirm `0.11.0a2` or document the compatibility reason for another increasing
  pre-release version.
- [ ] Update package metadata, changelog, support table, and migration documentation in
  one version-change commit.
- [ ] Record the exact 40-character source commit and `uv.lock` SHA-256 digest.
- [ ] Confirm `git status --porcelain` is empty and `git fsck --full` passes.
- [ ] Run `uv lock --check` without changing the lockfile.
- [ ] Verify all post-recovery commits use author and committer
  `mergen-institute <mergen-institute@users.noreply.github.com>` and sentence-case,
  three-to-seven-word subjects.

**Evidence:** candidate identity record containing version, source commit, lock digest,
branch, workflow run ID, and preparation timestamp.

**Done when:** one immutable source commit is selected and every downstream job consumes
that identity rather than a nearby checkout.

### A2. Produce canonical distributions

- [ ] Build wheel and sdist in the protected hosted workflow with `uv build --no-sources`.
- [ ] Reject extra files in `dist/`; accept only one wheel and one sdist for the selected
  version.
- [ ] Run Twine validation against the two explicit distribution paths.
- [ ] Generate SHA-256 digests and store them in the candidate identity record.
- [ ] Generate an SBOM and provenance attestation for both distributions.
- [ ] Download the hosted artifacts into a fresh verification job; do not rebuild them
  for downstream checks.
- [ ] Verify the downloaded digests before installation or execution.

**Evidence:** protected workflow URL/run ID, wheel and sdist digests, Twine output, SBOM
digest, and attestation identifiers.

**Done when:** the same two digest-verified files feed every remaining workstream.

## Workstream B — Artifact-bound runtime matrix

### B1. Isolate installed-package execution

- [ ] Create clean virtual environments outside the repository for the wheel and
  extracted sdist.
- [ ] Install with `--no-cache-dir` and verify `fastapi_mergen.__file__` is inside the
  clean environment, not the source checkout.
- [ ] Assert repository paths are absent from `PYTHONPATH` and the working directory.
- [ ] Verify base installation does not import optional dependencies.
- [ ] Verify each supported extra independently and then verify the all-extras set.
- [ ] Run `python -m fastapi_mergen --version`, CLI help, packaged schema checks, and
  `pip check` in every applicable environment.

**Evidence:** environment manifest with Python/platform/dependency versions and the
verified candidate digests.

### B2. Run PostgreSQL compatibility from the candidate

- [ ] Run the full integration selection on PostgreSQL 16 with exact generated
  migration, application, and relay roles.
- [ ] Run the same selection on PostgreSQL 18.
- [ ] Confirm there are no skipped integration tests in either report.
- [ ] Confirm the installed package, Alembic environment, CLI, Taskiq worker, and test
  helpers all resolve from the candidate installation.
- [ ] Capture PostgreSQL server versions, `asyncpg` version, SQLAlchemy version, schema
  revision registry, and runtime-role names.
- [ ] Retain JUnit plus a bounded human-readable summary for each database version.

**Evidence:** two candidate-bound JUnit reports and a matrix manifest keyed by source,
artifact, lock, database, driver, schema, and role configuration.

**Done when:** both database versions pass the same complete selection with zero
unreported skips.

### B3. Rehearse Taskiq through the installed artifact

- [ ] Start Redis and a separate Taskiq CLI worker from the clean candidate environment.
- [ ] Deliver delayed attempt A after parent reclamation and confirm zero handler
  admissions for A.
- [ ] Deliver current attempt B plus a queued duplicate and confirm exactly one handler
  execution.
- [ ] Expire an execution token, replace it, and confirm stale finalization cannot change
  parent or handoff state.
- [ ] Stall broker acknowledgement until the aggregate attempt deadline and confirm
  recovery remains bounded and duplicate-safe.
- [ ] Exercise graceful worker and relay shutdown with in-flight work.
- [ ] Record Redis server/client, Taskiq, broker, worker-process, and adapter versions.

**Evidence:** structured handoff state transitions, execution counters, worker-process
identity, bounded logs, and JUnit output tied to candidate digests.

**Done when:** the real Redis Streams/CLI-worker path proves stale rejection, current
execution, duplicate fencing, expiry replacement, and shutdown behavior.

### B4. Rehearse webhooks through the installed artifact

- [ ] Start a local TLS receiver with a private test CA and hostname certificate.
- [ ] Verify explicit-IP connection retains original-host SNI and Host header.
- [ ] Verify insecure or later-mutated TLS contexts fail before network I/O.
- [ ] Exercise mixed public/private DNS answers and confirm the complete answer set fails
  closed before address-attempt truncation.
- [ ] Exercise bounded multi-address failure, redirect re-resolution, informational
  responses, response bounds, slow close, and aggregate attempt timeout.
- [ ] Exercise public app-role lifecycle operations: create, rotate, pause/resume,
  replay, retention, and cross-tenant/unauthorized rejection.
- [ ] Confirm Retry-After HTTP dates use the post-response clock and cannot cross the
  delivery latest-finish deadline.
- [ ] Confirm response bodies, secret material, and unsafe endpoint details are absent
  from public evidence.

**Evidence:** candidate-bound security/JUnit reports, receiver observations, sanitized
transport event summaries, and PostgreSQL role/grant snapshot.

**Done when:** webhook delivery and lifecycle behavior pass through public APIs and real
network/database boundaries under the candidate installation.

### B5. Run remaining supported capability journeys

- [ ] Run atomic request → event → fan-out → relay → handler success.
- [ ] Run failure → retry → reconciliation → success and manual replay.
- [ ] Run command idempotency, conflict, expiry, pruning, and concurrent-generation
  scenarios.
- [ ] Run delegation issuance, non-expansion, audience/method/path binding, revocation,
  rotation, and downstream enforcement.
- [ ] Import and exercise the documented FastMCP bridge from its clean extra.
- [ ] Run doctor and every selected conformance profile against the candidate.

**Evidence:** candidate-bound journey report mapped to the capability ledger and
documentation inventory.

## Workstream C — Migration and recovery qualification

### C1. Verify the shipped revision chain

- [ ] Upgrade an empty database through revisions `0001` → `0005` one revision at a
  time on PostgreSQL 16 and 18.
- [ ] Seed representative protected data at each revision before upgrading further.
- [ ] Verify owners, grants, forced RLS, policies, constraints, indexes, functions, and
  triggers after every transition.
- [ ] Re-run the frozen migration-contract digest and mutable-import guard.
- [ ] Prove runtime ORM/helper changes cannot alter old revision output.
- [ ] Verify supported empty-schema downgrades and documented nonempty downgrade guards.

**Evidence:** per-revision schema/grant digests and JUnit reports for both PostgreSQL
versions.

### C2. Reconfirm historical artifact applicability

- [ ] Re-query PyPI, TestPyPI, repository releases/tags, protected workflow artifacts,
  and maintainer-retained distributions.
- [ ] Ask maintainers explicitly whether a private schema-bearing artifact exists.
- [ ] If one exists, install it, create and seed its schema, then upgrade using the exact
  candidate wheel on PostgreSQL 16 and 18.
- [ ] If none exists, refresh the `NOT_APPLICABLE` record with query timestamps,
  authenticated repository evidence where available, and maintainer confirmation.

**Evidence:** refreshed inventory; if applicable, protected-data and schema/grant
comparison before and after upgrade.

### C3. Rehearse backup and restore

- [ ] Create a representative database containing events, terminal and pending
  deliveries, attempts, replays, Taskiq handoffs, commands, subscriptions, encrypted
  secret versions, and audit entries.
- [ ] Take a logical backup using the documented operator procedure.
- [ ] Restore into a separate database under fresh runtime roles.
- [ ] Run schema checks, doctor, conformance, replay, relay, retention, and command replay
  against the restored database.
- [ ] Record recovery time, manual interventions, and any identity/digest mismatches.

**Evidence:** redacted backup/restore manifest and post-restore verification report.

**Done when:** revision upgrades and operational restore preserve protected data and
runtime guarantees on both supported database versions.

## Workstream D — Hosted gates and evidence integrity

### D1. Exercise protected workflows

- [ ] Run mandatory quality, packaging, integration, compatibility, and security jobs
  from the selected candidate commit.
- [ ] Confirm the shared check uses automatic readiness-phase selection.
- [ ] Run dependency audit, Bandit, repository security scan, license checks, SBOM
  generation, and provenance attestation.
- [ ] Confirm GitHub Actions are SHA-pinned and workflow permissions remain least
  privilege.
- [ ] Confirm release jobs cannot publish artifacts built in another run or after source
  changes.
- [ ] Test fail-closed behavior for missing services, missing artifacts, digest mismatch,
  malformed readiness evidence, and skipped jobs.

**Evidence:** immutable workflow run IDs, job conclusions, logs/artifacts retention
locations, and attestation identifiers.

### D2. Promote evidence stages precisely

- [ ] Update the machine-readable capability ledger from actual hosted outputs.
- [ ] Replace base-commit or working-tree language with the exact candidate identity.
- [ ] Promote only capabilities with direct hosted evidence to `HOSTED_VERIFIED`.
- [ ] Keep partner, independent-review, observation, and publication stages open.
- [ ] Validate every ledger path, digest, timestamp, dependency version, and owner.
- [ ] Regenerate the human-readable ledger from or reconcile it against the same facts.
- [ ] Review the findings register; attach hosted regressions to F01–F18 and reopen any
  contradicted disposition.

**Done when:** another maintainer can reproduce every hosted claim from the ledger
without relying on private chat or an untracked file.

## Workstream E — Documentation and support-surface freeze

### E1. Execute the maintained documentation inventory

- [ ] Re-scan every executable-language block and resolve inventory drift.
- [ ] Execute installation, quickstart, relay, webhook lifecycle, replay, Taskiq, and
  FastMCP journeys from the downloaded candidate artifacts.
- [ ] Keep executed, syntax-checked, manual/operator-only, and historical classifications
  separate.
- [ ] Record exact block hash, command, environment, result, and evidence path.
- [ ] Remove or correct instructions that need the repository checkout when the public
  package should suffice.
- [ ] Confirm all local Markdown links and referenced evidence paths resolve.

### E2. Freeze the beta support table

- [ ] Classify core PostgreSQL runtime, in-process handlers, webhooks, Taskiq, commands,
  delegation, and FastMCP as stable-beta, experimental, reference-only, or unsupported.
- [ ] Keep Taskiq and delegation experimental unless their specific artifact/hosted
  gates pass without caveat.
- [ ] State supported Python, PostgreSQL, Redis, FastAPI, SQLAlchemy, Taskiq, and FastMCP
  ranges from tested evidence.
- [ ] Document compatibility, upgrade, rollback, retention, backup/restore, timeout,
  retry, and shutdown limits.
- [ ] Provide one minimal installation/tutorial path that does not require unrelated
  optional frameworks.
- [ ] Ensure README, public API reference, changelog, migration guide, and capability
  ledger agree.

**Done when:** the advertised beta surface is narrower than or equal to the directly
verified candidate surface, with experimental boundaries explicit.

## Workstream F — Prepare later external gates

These tasks prepare R3/R4 work but do not complete it internally.

- [ ] Assign an owner for partner recruitment and an owner for independent review.
- [ ] Prepare a redacted design-partner evidence template covering all mandatory
  exercises and selected capabilities.
- [ ] Define production-like equivalence criteria for scale, traffic, managed services,
  failure injection, operational ownership, and observation duration.
- [ ] Define secure evidence transfer, retention, access, and disclosure procedures.
- [ ] Identify two partners with distinct organizations or genuinely independent
  environment owners; do not count two environments run by the maintainer.
- [ ] Prepare the independent review scope for RLS/grants, stale-worker fencing, webhook
  SSRF/TLS, secret lifecycle, replay, commands, delegation, and evidence redaction.
- [ ] Define RC observation duration, workload, reset conditions, blocker severity, and
  the two-person approval policy before observation starts.
- [ ] Leave readiness-record partner/review/observation fields empty until real evidence
  and approvals exist.

## Recommended execution order

1. A1 candidate selection and identity.
2. A2 canonical protected artifact build.
3. B1 isolated installation proof.
4. B2–B5 runtime journeys, parallelized only where evidence remains unambiguous.
5. C1–C3 migration and recovery qualification.
6. D1 hosted failure/success gates.
7. D2 evidence promotion and findings reconciliation.
8. E1 documentation execution.
9. E2 beta support-surface freeze.
10. F external-gate preparation and owner assignment.

Any source, lockfile, migration, workflow, or public-documentation change after A2
invalidates the candidate and restarts from A1.

## Phase exit criteria

- [ ] A clean, immutable source commit and exactly one wheel/sdist pair are bound by
  SHA-256 digests.
- [ ] Protected hosted quality, security, packaging, PostgreSQL 16/18, Redis/Taskiq,
  migration, and conformance gates all pass against that identity.
- [ ] Every supported documentation journey is executed from the exact artifacts or is
  explicitly classified as manual/historical with a reason.
- [ ] No infrastructure test is skipped or silently downgraded.
- [ ] F01–F18 remain fixed under hosted regression coverage; any new finding is recorded
  with owner, severity, target, disposition, and regression evidence.
- [ ] The capability ledger and evidence bundle contain source, lock, artifact,
  infrastructure, dependency, command, result, timestamp, and owner bindings.
- [ ] The beta support table includes only capabilities proven by the candidate evidence.
- [ ] The production-readiness record remains `no-go` unless later external gates have
  independently supplied valid evidence.
- [ ] R2.3, R2.4, and R3.1 are checked only after their complete acceptance paragraphs
  are satisfied.

Completion of this phase authorizes starting partner validation. It does not authorize
v1 publication.

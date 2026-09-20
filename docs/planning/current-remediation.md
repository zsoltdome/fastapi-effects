# Current remediation status

**Baseline:** `0.11.0a1`, committed local-verification source
`24503cdcaf5cc204534e3aa8d8ec476804dcb11d`
**Audit-origin record:** internal planning narratives are supplementary inputs, not
public documentation dependencies. The clean historical summary and unavailable
evidence classification are recorded in
[`docs/audits/2026-09-07/evidence-status.json`](../audits/2026-09-07/evidence-status.json).

## 2026-09-13 audit correction status

The later adversarial audit invalidated only the affected edges of earlier findings;
historical evidence remains retained but is not treated as proof of the new boundaries.

- **A01 — IMPLEMENTED:** Unicode IRI path/query input is converted once to an ASCII
  URI while existing escapes are retained. Bad durable endpoints and redirects are
  terminal per-delivery errors. Direct and concurrent-relay regressions are local.
- **A02 — IMPLEMENTED:** reconcile, claim, finalization, Taskiq control work, and relay
  shutdown have separate cooperative budgets. SIGTERM and SIGINT are exercised in a
  subprocess. Live database cleanup/ambiguous-commit rehearsals remain required.
- **A03 — IMPLEMENTED:** reviewed invalidated-connection and SQLSTATE classification
  replaces the narrow exception tuple; programming/schema defects still escape.
  Persistent-storage restart rehearsals pass locally on PostgreSQL 16 and 18; live
  backend termination/restart across every boundary remains required.
- **A04 — IMPLEMENTED:** PostgreSQL `clock_timestamp()` is sampled after finalization
  locks and drives recorded transition time. Real lock-delay and application-clock-skew
  tests pass locally on PostgreSQL 16 and 18, but must be rerun from the candidate artifact.
- **A05 — IMPLEMENTED:** semantic PEP 440 phase selection covers later RC/stable
  releases and fails closed on unsupported forms or explicit-phase mismatch.
- **A06 — IMPLEMENTED:** one manifest-bound wheel/sdist set is uploaded by the evidence
  workflow and downloaded/verified by publication without rebuilding. Hosted
  environment and trusted-publisher settings still require account-level verification.
- **A07/A08 — IMPLEMENTED:** contributor CI no longer enforces institute impersonation;
  the invoicing consumer is transactionally idempotent and uses process-lifetime,
  role-separated pools.
- **A09/A10 — IMPLEMENTED:** the quickstart is an installed-wheel persistent journey,
  the packaged schema-upgrade command and supported PostgreSQL composition surface are
  documented, and the sdist intentionally includes downstream test/document resources.

These entries remain below `HOSTED_VERIFIED`; no external account, protected
environment, publication, or partner evidence is inferred from local source changes.

## Historical local verification at the source commit above

- [x] F01 stale Taskiq handoff admission is fenced against the current parent attempt.
- [x] F02 expected success/failure lease loss is isolated per delivery; the reviewed
  SQLAlchemy failure set was locally exercised. This historical entry did not cover raw
  connector exceptions before SQLAlchemy wrapping.
- [x] F03 one aggregate attempt budget covers dependency, transport, broker, execution,
  and cleanup waits; address and redirect counts are bounded.
- [x] F04 maximum elapsed time is defined and enforced as a latest-finish deadline.
- [x] F05 least-privilege tenant replay works through the public FastAPI path on the
  exact application grant without widening it to `UPDATE`.
- [x] F06 RC/final release auditing is phase-aware.
- [x] F07 production TLS contexts are validated before every I/O and custom CAs retain
  hostname/SNI verification.
- [x] F08 informational HTTP responses are consumed until a final response under shared
  bounds; upgrades are explicitly unsupported.
- [x] F09 revisions `0001`–`0005` use frozen DDL/security definitions with a golden
  contract digest.
- [x] F10 has a stage-aware evidence ledger, an exhaustive content-bound Markdown
  inventory, resolvable governing sources, and explicit unavailable-evidence records.
- [x] F11 readiness records fail closed on malformed, duplicate, unresolved, or
  candidate-mismatched partner/review/observation/approval evidence.
- [x] F12 closure-scoped FastAPI dependencies in the webhook router resolve correctly.
- [x] F13 Git governance preserves the exact documented recovery-baseline identity
  exception while enforcing current author/subject rules for all later commits.
- [x] F14 the local release gate selects only wheel/sdist distributions for Twine;
  `dist/.gitignore` and unrelated metadata are excluded by regression test.
- [x] F15 address-attempt limiting validates the complete DNS answer set first, so a
  disallowed answer outside the attempted prefix still fails closed.
- [x] F16 the shared release check selects its readiness phase automatically instead of
  forcing populated RC/final records through pre-v1 validation.
- [x] F17 finalization rejects an elapsed lease without waiting for reconciliation, and
  success independently fences handler and delivery latest-finish deadlines.
- [x] F18 evidence references are repository-relative, repository-contained after
  resolution, and present; absolute or traversal references fail the shared gate.
- [x] The stale-old/current Taskiq scenario passes through Redis Streams and one
  separately started Taskiq CLI worker; stale A admits no handler and current B runs
  exactly once despite a queued duplicate.
- [x] The published-artifact inventory found no public index release, repository tag,
  or retained historical distribution, so historical-artifact upgrade testing is
  explicitly `NOT_APPLICABLE`; every candidate revision is still covered.
- [x] The full integration selection passes locally on PostgreSQL 16 and 18: 45 tests
  on each version, with no skipped integration tests.
- [x] Clean wheel/sdist installation checks pass for the base package and supported
  extras, followed by Twine validation of both distribution files.
- [x] Every one of the 40 executable-language Markdown blocks is classified and
  content-hashed, and all seven required documentation journeys have local evidence.

## Still open

The 2026-09-20 recheck is tracked separately under
[`docs/audits/2026-09-20/README.md`](../audits/2026-09-20/README.md). Its source fixes
and regressions do not inherit the historical `LOCAL_VERIFIED` label until run against
the recorded candidate and required live/hosted profiles.

- [ ] Promote the committed source identity to a versioned candidate, build it through
  the protected workflow, and rerun the database-backed quickstart, relay, webhook
  lifecycle/replay, and Taskiq journeys from those exact artifacts.
- [ ] Bind protected results to the candidate artifact digests and obtain hosted
  verification, security scans, SBOM, and provenance.
- [ ] Complete two distinct non-demo external deployments, independent review, exact-RC
  observation, and two-person go approval. The production-readiness record remains
  deliberately `no-go` until these exist.

See [the capability ledger](capability-evidence-ledger.md) and
[findings register](../security-review/findings.md) for stage-specific status and
evidence limits.

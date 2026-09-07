# Current remediation status

**Baseline:** `0.11.0a1`, committed local-verification source
`24503cdcaf5cc204534e3aa8d8ec476804dcb11d`
**Detailed audit-origin plan:** the supplied `sup/audit_road.md`, `sup/remediation.md`,
`sup/plan.md`, and `sup/todo.md` now have explicit Git-trackable exceptions. The missing
ZIP and evidence files are governed as unavailable in
[`docs/audits/2026-09-07/evidence-status.json`](../audits/2026-09-07/evidence-status.json).

## Locally verified at the source commit above

- [x] F01 stale Taskiq handoff admission is fenced against the current parent attempt.
- [x] F02 expected success/failure lease loss is isolated per delivery; transient DB
  connection failure does not stop the supervisor.
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

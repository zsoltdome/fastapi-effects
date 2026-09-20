# Historical audit evidence status

The original planning narratives are retained as internal supplementary material, but
they are not public documentation dependencies. This clean record captures the parts
needed to interpret the audit and its evidence classification.

The ZIP and eight evidence paths described by the audit were not present in the
workspace received for remediation. The audit now marks them unavailable explicitly;
its historical archive hash and probe results must not be treated as independently
resolved evidence. Current implementation claims instead use ordinary regression,
live-infrastructure, packaging, and readiness-gate results listed in the
[capability ledger](../../planning/capability-evidence-ledger.md).

If the original bundle is recovered later, add it without secrets, record each file's
SHA-256 digest, bind it to the claimed archive and source revision, and replace the
`unavailable` classifications. Never infer recovered evidence from matching prose.

The separate [`published-artifact-inventory.json`](published-artifact-inventory.json)
records the public-index, release-endpoint, repository-tag, and retained-file inventory
used for migration testing. No historical schema-bearing distribution was identifiable,
so historical artifact upgrade testing is `NOT_APPLICABLE`; every revision shipped in
the current candidate is still seeded and upgraded in the PostgreSQL 16/18 matrix.

[`local-verification.json`](local-verification.json) records the exact local commands,
versions, infrastructure, results, source commit, and non-authoritative wheel/sdist
hashes. It deliberately sets `release_evidence_authority` to false because the checks
and artifact build were local rather than produced by the protected workflow.

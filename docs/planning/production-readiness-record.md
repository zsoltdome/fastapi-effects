# Production readiness record

The machine record is `production-readiness-record.json`. It intentionally contains no
partner completions, independent review, or RC observation yet. The current v1 decision
is therefore **no-go**. Populate it only from the design-partner protocol; local CI must
not synthesize these fields.

Before RC evaluation, bind `candidate_version`, `candidate_source_commit`,
`candidate_artifact_digests`, and `selected_capabilities`. Digests are lower-case,
64-character SHA-256 values. The observation record repeats the candidate binding so an
observation cannot silently be applied to another build.
Capability lists are unique and bounded to 32 entries. Candidate artifacts, partner
evidence, and independent-review evidence use lower-case SHA-256 digests.

For each partner object, use `id`, `environment_owner`, `status`, `deployment_class`,
`capabilities`, `exercises`, `evidence_ids`, `evidence_digest`, `issues`,
`approved_by_partner`, and `approved_by_maintainer`. Completed partners must have distinct
IDs, environment owners, and evidence digests. Permitted live deployment classes are
`production`, `production_like`, and `live_staging`; demos and maintainer-owned duplicate
environments do not qualify.

The mandatory exercise IDs are `schema_check`, `doctor`, `conformance`, `migration`,
`backup_restore`, `relay`, `retry_reconciliation`, `manual_replay`, `retention`, and
`incident`. A completed partner covers every selected capability and exercise, has no
unresolved critical/high or contract-breaking issue, supplies bounded evidence IDs and a
valid digest, and receives both approvals. Capability, exercise, and evidence-ID lists
must contain unique bounded identifiers; each list is capped at 64 entries. Issue lists
are capped at 100 structured dispositions. Independent-review evidence, a valid RC
observation interval, and two distinct final approvers are validated by the release gate.

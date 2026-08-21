# Production readiness record

The machine record is `production-readiness-record.json`. It intentionally contains no
partner completions, independent review, or RC observation yet. The current v1 decision
is therefore **no-go**. Populate it only from the design-partner protocol; local CI must
not synthesize these fields.

For each partner object, use `id`, `status`, `deployment_class`, `capabilities`,
`evidence_ids`, `evidence_digest`, `issues`, `approved_by_partner`, and
`approved_by_maintainer`. A completed partner requires `status: complete`, a non-demo live
deployment class, all mandatory exercises, a bounded SHA-256 evidence digest, and both
approvals.

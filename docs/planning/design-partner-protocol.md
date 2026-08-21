# Design-partner validation protocol

v1 requires two independent, serious live deployments. A maintainer cannot substitute
local tests, a demo, or two deployments owned by the same team.

For each partner, record a pseudonymous ID, environment owner, workload and capabilities,
Python/PostgreSQL/dependency evidence IDs, schema before/after, deployment dates, and
links to private evidence. The partner must execute schema check, doctor, applicable real
conformance profiles, migration, verified backup/restore, normal relay operation,
retry/reconciliation, manual replay, retention, and one incident exercise.

Capture event volume, tenants, backlog/retry/dead behavior, ambiguous outcomes,
operational toil, API/documentation friction, and category fit. Convert every observation
to an issue with severity, owner, disposition, and target release. Contract-breaking and
critical/high security findings block promotion.

Never commit partner names, DSNs, credentials, payloads, tenant identifiers, signing
material, or raw production logs. Store sensitive evidence in the approved private
system and commit only bounded digests/status. Both partner and maintainer approve the
readiness record.

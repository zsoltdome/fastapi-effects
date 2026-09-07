# Capability and evidence ledger

This ledger separates implementation from local, hosted, external, and release evidence.
The local verification is bound to source commit
`24503cdcaf5cc204534e3aa8d8ec476804dcb11d`. Its results are reproducible local
evidence, but they are not protected hosted or release evidence. A local wheel and
sdist were built from that commit and verified; their hashes remain non-authoritative
until the candidate is built by the protected workflow. The lock digest is
`b7fd3f0a58418806d1c39922c4899cef0d9ea45ef68bedd0425973aee9b3e3df`.
The local verification record is
[`docs/audits/2026-09-07/local-verification.json`](../audits/2026-09-07/local-verification.json).

| Capability | Owner | Status | Local result | Still required |
| --- | --- | --- | --- | --- |
| Core PostgreSQL/UoW/relay | maintainer | LOCAL_VERIFIED | PostgreSQL 16/18 integration selections pass with exact generated app/relay/migration roles and no skips; success and failure finalization reject expired leases before reconciliation, and success also fences its handler/delivery deadline | committed source, hosted matrix, candidate artifact binding |
| Webhook operations/transport | maintainer | LOCAL_VERIFIED | App-role public replay and concurrent retention, aggregate budgets including a live stalled socket, complete-answer-set DNS validation before attempt limiting, TLS custom CA/policy, HTTP informational responses, and both PostgreSQL versions passed | hosted network rehearsal and design-partner deployment |
| Taskiq executor | maintainer | LOCAL_VERIFIED | Redis Streams delivered stale A after parent reclaim to a separate Taskiq CLI worker: A admitted zero handlers, current B executed once, and its queued duplicate was fenced; execution-token replacement also rejects stale finalization | committed source, hosted matrix, installed-candidate execution |
| Command idempotency | maintainer | LOCAL_VERIFIED | Both PostgreSQL integration selections pass | candidate artifact and hosted compatibility matrix |
| Delegation/FastMCP | maintainer | LOCAL_VERIFIED | Existing local conformance/integration selection passes | installed-artifact and hosted compatibility evidence |
| Published migration contract | maintainer | LOCAL_VERIFIED | All candidate revisions upgrade with seeded data on PostgreSQL 16/18; golden frozen-definition digest and unsupported-downgrade guard pass; the public/tag/retained-artifact inventory found no historical schema-bearing artifact and records historical-artifact upgrade as `NOT_APPLICABLE` | candidate-wheel matrix and hosted evidence |
| RC/final readiness gate | maintainer | LOCAL_VERIFIED | Phase table and malformed/duplicate/mismatched evidence fixtures pass; `scripts/check.py` and tagged workflows use automatic phase selection; Git governance accepts only the documented recovery-baseline exception | actual workflow run against a committed candidate |
| Packaging | maintainer | LOCAL_VERIFIED | Clean wheel/sdist installs passed for the base package and supported extras; Twine accepted both distribution files | committed candidate, protected build, provenance, candidate-bound hashes |
| Documentation journeys | maintainer | LOCAL_VERIFIED | All 40 executable-language Markdown blocks are content-bound in a maintained inventory; evidence paths are constrained to the repository; all seven required journeys have explicit local evidence, including clean artifact install and FastMCP import | rerun the database-backed journeys from the exact committed candidate artifacts |
| Hosted CI/security/provenance | maintainer | OPEN | Not run for the locally verified commit | protected hosted checks, scans, SBOM and attestations |
| Partner 1 / Partner 2 / independent review / RC observation | external owners unassigned | OPEN | Not applicable to local tests | two distinct non-demo live environments, independent review, exact-candidate observation and approvals |

Machine-readable fields and exact commands are in
[`capability-evidence-ledger.json`](capability-evidence-ledger.json). Promotion must not
infer a later stage from an earlier-stage result.

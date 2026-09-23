# Capability and evidence ledger

This ledger separates implementation from local, hosted, external, and release evidence.
The historical local verification remains bound to commit
`24503cdcaf5cc204534e3aa8d8ec476804dcb11d` and is retained in
[`docs/audits/2026-09-07/local-verification.json`](../audits/2026-09-07/local-verification.json).
The released `0.11.0a1` evidence is bound to tag `v0.11.0a1`, source commit
`575f4f97769fdf6b3152822096ee1cae2668f0bf`, release-evidence run `35539365216.1`,
publish run `35540231354.1`, and the public artifact hashes in the
[September 23 release inventory](../audits/2026-09-23/release-inventory.json). Capability
stages requiring partner deployment or independent review are not promoted merely
because an alpha was published.

| Capability | Owner | Status | Local result | Still required |
| --- | --- | --- | --- | --- |
| Core PostgreSQL/UoW/relay | maintainer | HOSTED_VERIFIED | PostgreSQL 16/18 hosted integration selections passed; the tag run repeated the PostgreSQL 18 integration and exact-artifact runtime journeys | external deployment and next-candidate rerun |
| Webhook operations/transport | maintainer | HOSTED_VERIFIED | Hosted security, PostgreSQL 16/18, installed-artifact receiver, and replay journeys passed | hosted network rehearsal and design-partner deployment |
| Taskiq executor | maintainer | HOSTED_VERIFIED | Hosted PostgreSQL/Redis and separately executed worker coverage passed for the released commit | design-partner deployment and next-candidate execution |
| Command idempotency | maintainer | HOSTED_VERIFIED | Hosted PostgreSQL 16/18 integration and installed-artifact invoicing journeys passed | external deployment evidence |
| Delegation/FastMCP | maintainer | HOSTED_VERIFIED | Hosted conformance/security tests and installed-artifact FastMCP import passed with the released lock | explicit latest-supported-major bridge execution and external use |
| Published migration contract | maintainer | HOSTED_VERIFIED | Candidate revisions and frozen definitions passed in hosted PostgreSQL 16/18 jobs; `0.11.0a1` is now the required public baseline for every later candidate | exact public-wheel to candidate-wheel upgrade on PostgreSQL 16/18 |
| RC/final readiness gate | maintainer | HOSTED_VERIFIED | Automatic phase selection and evidence validation passed in the tag workflow | rerun for the next version and RC/final-specific evidence |
| Packaging | maintainer | RELEASED | The manifest-bound wheel and sdist were attested, reverified without rebuilding, and published by Trusted Publishing; public hashes match the immutable workflow artifact | repeat through the approval-gated path for the next version |
| Documentation journeys | maintainer | HOSTED_VERIFIED | Documentation checks and selected exact-artifact database journeys passed in hosted workflows | rerun all required journeys from the next candidate artifacts |
| Hosted CI/security/provenance | maintainer | RELEASED | Hosted checks, scans, SBOM, GitHub SLSA provenance, and two PyPI publish attestations are bound to `0.11.0a1` | repeat after protection changes for the next version |
| Partner 1 / Partner 2 / independent review / RC observation | external owners unassigned | OPEN | Not applicable to local tests | two distinct non-demo live environments, independent review, exact-candidate observation and approvals |

Machine-readable fields and exact commands are in
[`capability-evidence-ledger.json`](capability-evidence-ledger.json). Promotion must not
infer a later stage from an earlier-stage result.

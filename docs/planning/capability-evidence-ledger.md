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

The protected `0.11.0a2` candidate is separately bound to tag `v0.11.0a2`, source
commit `28f2e4d58d0ea03eda9e9acd031c92602b42c091`, release-evidence run
`35876379003.2`, wheel SHA-256
`ca1028f7ad90967ee40657295648d56ac69fc95db7fde6a34976911348a63d24`, and sdist
SHA-256 `e7ab5fde92e72d0f3d0209cb0675896d990b3f77ab6c781253e67fd1afe7ff58`.
Its [candidate inventory](../audits/2026-09-23/release-inventory-v0.11.0a2.json)
records exact-artifact and public-`0.11.0a1` upgrade results plus verified GitHub SLSA
provenance. It is not promoted to `RELEASED` until the human FE-008 gate, GitHub
release, protected PyPI publish, public-byte verification, and both PyPI file
attestations are complete.

| Capability | Owner | Status | Local result | Still required |
| --- | --- | --- | --- | --- |
| Core PostgreSQL/UoW/relay | maintainer | HOSTED_VERIFIED | PostgreSQL 16/18 hosted selections passed; the `0.11.0a2` tag run repeated T05/T09, restart, and exact wheel/sdist runtime journeys | external deployment |
| Webhook operations/transport | maintainer | HOSTED_VERIFIED | Hosted security and PostgreSQL 16/18 checks passed; the exact candidate artifacts ran receiver, replay, key-lifecycle, and fault journeys | hosted network rehearsal and design-partner deployment |
| Taskiq executor | maintainer | HOSTED_VERIFIED | Hosted PostgreSQL/Redis and separate-worker coverage passed; the exact candidate artifacts repeated duplicate fencing and context cleanup | design-partner deployment |
| Command idempotency | maintainer | HOSTED_VERIFIED | Hosted PostgreSQL 16/18 integration and installed-artifact invoicing journeys passed | external deployment evidence |
| Delegation/FastMCP | maintainer | HOSTED_VERIFIED | Hosted conformance/security tests passed at FastMCP 3.4.7 and 4.0.5; exact candidate imports passed with the retained lock | external use |
| Published migration contract | maintainer | HOSTED_VERIFIED | The exact public `0.11.0a1` wheel created and seeded each database before the exact candidate upgraded it; 14 ownership, role, grant, forced-RLS, constraint, index, data, and revision checks passed on PostgreSQL 16.15 and 18.6 | repeat from public `0.11.0a2` for the next candidate |
| RC/final readiness gate | maintainer | HOSTED_VERIFIED | Automatic phase selection and pre-v1 evidence validation passed in protected run `35876379003.2` | RC/final-specific external evidence |
| Packaging | maintainer | RELEASED | `0.11.0a1` is released; the `0.11.0a2` manifest-bound wheel/sdist passed the protected artifact path and GitHub provenance verification | FE-008, durable GitHub release assets, protected PyPI publish, and public-byte verification |
| Documentation journeys | maintainer | HOSTED_VERIFIED | Documentation checks and selected journeys passed from both exact `0.11.0a2` artifact forms | unfamiliar-developer FE-008 record |
| Hosted CI/security/provenance | maintainer | RELEASED | `0.11.0a1` has GitHub provenance and two PyPI attestations; `0.11.0a2` has protected hosted checks, SBOM, and verified GitHub SLSA provenance | `0.11.0a2` PyPI publish run and both file attestations |
| Partner 1 / Partner 2 / independent review / RC observation | external owners unassigned | OPEN | Not applicable to local tests | two distinct non-demo live environments, independent review, exact-candidate observation and approvals |

Machine-readable fields and exact commands are in
[`capability-evidence-ledger.json`](capability-evidence-ledger.json). Promotion must not
infer a later stage from an earlier-stage result.

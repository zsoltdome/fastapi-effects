# Security review register

The internal adversarial review covers these trust boundaries:

| Capability | Primary model | Executable controls |
| --- | --- | --- |
| Core/UoW/relay/RLS | `docs/concepts/threat-model.md` | security, concurrency, migration, and core conformance tests |
| Webhooks/SSRF/secrets | threat-model webhook sections | hostile DNS/IP, response bounds, crypto rotation, ambiguous-success chaos |
| Taskiq | `ADR-011` and executor boundary | stable task ID, duplicate fencing, expired execution token |
| Commands | `ADR-012` | fingerprint/conflict, transaction rollback, response bounds, pruning grants |
| Delegation/FastMCP | delegation threat model and `ADR-013` | target binding, header stripping, scope/depth, rotation/revocation, audit redaction |
| Evidence/telemetry | conformance and observability references | canaries, attribute allowlists, atomic private reports |

Internal review on 2026-08-30 found no known unresolved critical or high issue after the
listed controls. This statement is repository review evidence, not an independent audit.
The release-candidate gate requires all scanners, real PostgreSQL profiles, artifact
smokes, SBOM, provenance, and the findings register to be green.

Bandit's repository policy accepts three reviewed detector exclusions in `bandit.yaml`:
`B105` misclassifies bounded status/contract enum values as passwords; `B405` flags the
standard-library XML builder even though it only creates JUnit output and never parses
input; and `B608` flags SQL composed from fixed schema constants or identifiers that pass
the runtime identifier validator. SQL values remain bound parameters, and hostile role,
table, and tenant inputs have dedicated tests. Assertions remain enabled in the scan so
optimized Python cannot silently remove runtime validation.

Accepted residual risks are at-least-once duplicate external effects, application-role
credential compromise within one tenant context, operator-controlled migration/relay
credentials, in-memory delegation keys in the reference implementation, and external DNS,
certificate, broker, key-provider, and PostgreSQL availability.

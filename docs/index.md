# FastAPI-Mergen documentation

FastAPI-Mergen defines a transaction boundary and executable assurance contract for
**tenant-safe effects** in FastAPI systems.

> **One commit. Every effect keeps its tenant and authority provenance.**

Version `0.11.0a1` is the production-hardening alpha. The repository now includes the
real PostgreSQL runtime, webhooks, Taskiq handoffs, command idempotency, target-bound
delegation/FastMCP, and their executable conformance profiles. v1 promotion remains
blocked on external partner, independent review, and RC observation evidence.

## Read in this order

1. [PostgreSQL quickstart](tutorials/quickstart.md) — real atomic delivery.
2. [Boundary Contract v1](concepts/boundary-contract.md) — normative invariants.
3. [Conformance and assurance](concepts/conformance.md) — executable model and limits.
4. [Guarantees](concepts/guarantees.md) — atomicity, retry, replay, and consumer
   deduplication terminology.
5. [Threat model](concepts/threat-model.md) — trust assumptions and residual risk.
6. [Authorization](concepts/authorization.md) — snapshot, revalidation, and named
   service authority.
7. [Production operations](operations/migrations.md) — migration through incident recovery.
8. [Certification operations](operations/certification.md) — running and retaining
   evidence.
9. [Public API](reference/public-api.md) — frozen symbols and deprecation policy.
10. [Conformance API](reference/conformance-api.md) — public assurance types and
   protocols.
11. [Architecture decisions](adr/README.md) — frozen choices and rejected alternatives.

## Assurance status

- **Normative:** Boundary Contract v1 and certification semantics.
- **Executable:** reference driver, profiles, scenarios, reporters, CLI, and audit.
- **Implemented:** PostgreSQL, handlers, webhook, Taskiq, command, and delegation paths.
- **Externally blocked:** production partner validation, independent review, RC
  observation, and trusted publication.
- **Not claimed:** formal verification or universal exactly-once effects.

# FastAPI-Mergen documentation

FastAPI-Mergen defines a transaction boundary and executable assurance contract for
**tenant-safe effects** in FastAPI systems.

> **One commit. Every effect keeps its tenant and authority provenance.**

Version `0.6.0a1` is the Milestone 7 assurance release. The production runtime remains
adapter-defined; this repository supplies the specification oracle, protocols,
scenarios, evidence formats, and certification rules.

## Read in this order

1. [Boundary Contract v1](concepts/boundary-contract.md) — normative invariants.
2. [Conformance and assurance](concepts/conformance.md) — executable model and limits.
3. [Guarantees](concepts/guarantees.md) — atomicity, retry, replay, and consumer
   deduplication terminology.
4. [Threat model](concepts/threat-model.md) — trust assumptions and residual risk.
5. [Authorization](concepts/authorization.md) — snapshot, revalidation, and named
   service authority.
6. [Certification operations](operations/certification.md) — running and retaining
   evidence.
7. [Conformance API](reference/conformance-api.md) — public assurance types and
   protocols.
8. [Architecture decisions](adr/README.md) — frozen choices and rejected alternatives.

## Assurance status

- **Normative:** Boundary Contract v1 and certification semantics.
- **Executable:** reference driver, profiles, scenarios, reporters, CLI, and audit.
- **Adapter-defined:** production PostgreSQL, executor, webhook, idempotency, or
  delegation implementation under test.
- **Not claimed:** formal verification or universal exactly-once effects.

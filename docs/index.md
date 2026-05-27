# FastAPI-Mergen documentation

FastAPI-Mergen is a planned transaction boundary for **tenant-safe effects** in
async FastAPI, SQLAlchemy 2.x, and PostgreSQL applications.

> **One commit. Every effect keeps its tenant and authority provenance.**

Version `0.0.1` is Milestone 1: a specification, repository foundation, safe API
spike, PostgreSQL test harness, and reference-application skeleton. It is not a
production implementation.

## Read in this order

1. [Boundary Contract](concepts/boundary-contract.md) — normative invariants and
   scope.
2. [Guarantees](concepts/guarantees.md) — exact meanings of atomicity, retry,
   replay, and consumer deduplication.
3. [Threat model](concepts/threat-model.md) — trust assumptions and residual risk.
4. [Authorization](concepts/authorization.md) — snapshot, revalidation, and named
   service authority.
5. [Roles and RLS](operations/roles-and-rls.md) — database trust separation.
6. [Relay](operations/relay.md) and [Retries and replay](operations/retries-and-replay.md)
   — delivery state and crash behavior.
7. [Architecture decisions](adr/README.md) — frozen choices and rejected alternatives.

## Scope through the Minimum Differentiated Product

Included through Milestone 3:

- trusted principal ingestion;
- explicit async SQLAlchemy unit of work;
- PostgreSQL event, delivery, and attempt records;
- forced RLS and three separated database roles;
- exact event-type routing with immutable destination and policy snapshots;
- polling relay with token-checked leases;
- in-process async handlers using fresh tenant-bound sessions;
- signed, retried outbound webhooks with safe transport;
- diagnostics, replay, dead-letter operations, and conformance tests.

Excluded:

- authentication and tenant lifecycle;
- a general task queue or workflow engine;
- ordering, cancellation, timers, DAGs, or compensation;
- inbound HTTP idempotency;
- MCP/delegation and external executor adapters;
- synchronous SQLAlchemy, non-PostgreSQL stores, or an admin UI.

## Status labels

- **Normative:** binding on future implementation and conformance tests.
- **API spike:** importable shape that deliberately raises before security-critical
  behavior.
- **Planned:** belongs to a later milestone and is not claimed by `0.0.1`.

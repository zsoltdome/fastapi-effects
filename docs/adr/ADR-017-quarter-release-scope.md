# ADR-017: Narrow core and webhook release scope

## Status

Accepted on 2026-09-23 for the September–December 2026 release sequence.

## Context

FastAPI Effects already ships a broad alpha: the PostgreSQL unit-of-work and relay,
signed webhooks, Taskiq handoff, command idempotency, delegation, FastMCP composition,
observability, and conformance. Those areas do not all have the same maturity. Python
signature stability, persisted database compatibility, security invariants, and
operational support are also different promises.

The corrected alpha needs one coherent adoption path. Expanding every optional helper
surface at the same time would make the later beta freeze and independent review less
credible. Narrowing the release focus must not silently remove already documented v1
targets or reduce regression coverage for shipped alpha features.

## Decision

The stable target for this quarter is the transactional PostgreSQL and signed-webhook
journey:

1. an application-owned SQLAlchemy transaction commits business state and immutable
   effect intent together;
2. tenant and authority context, PostgreSQL roles, grants, and forced RLS remain
   security boundaries;
3. fenced delivery, retry, attempt history, and accountable manual replay preserve
   their identity rules; and
4. the signed-webhook path preserves secret isolation, bounded networking, receiver
   verification, retention, and recovery behavior.

The following matrix governs documentation, onboarding, review, and release evidence.
“Stable target” means intended for the narrow v1 freeze after the roadmap gates pass;
it does not turn an alpha into a stable release.

| Surface | Quarter classification | Compatibility obligation |
| --- | --- | --- |
| Root runtime values and errors documented in the public API inventory | Stable target | Compatible Python API and stable error codes |
| `fastapi_effects.postgres` and `fastapi_effects.sqlalchemy` documented composition | Stable target | Compatible Python API plus preserved transaction, schema, role, RLS, lease, and identity contracts |
| `doctor`, `schema`, and polling `relay` commands | Stable target | Compatible CLI meaning and least-privilege operation |
| Signed-webhook persisted schema, route snapshots, security invariants, and operator journey | Stable target | Migration compatibility and preserved tenant, key, network, retry, and replay boundaries |
| Webhook Python implementation helpers | Provisional | Compatible refinements are allowed before freeze; persisted/security contracts cannot be weakened |
| Taskiq handoff, command idempotency, delegation, and FastMCP helper APIs | Provisional | Existing documented v1 targets are retained; alpha helper signatures may receive compatible refinements and all shipped security/recovery regressions remain required |
| Observability and conformance helper APIs outside their versioned evidence formats | Provisional | Versioned formats and bounded names remain contractual; convenience APIs can be refined compatibly |
| ORM rows, repositories, migration implementation helpers, DBAPI objects, transports, and unlisted modules | Internal | No direct compatibility promise; changes still may not violate a public or persisted contract |

The public API inventory describes both the narrow quarter target and already documented
future-v1 namespace commitments. A provisional classification does not authorize a
breaking deletion. Any narrowing of an existing commitment follows the deprecation
policy. Optional integrations remain in compatibility, security, and recovery testing
even when their helper APIs are outside this quarter's freeze.

## Consequences

- The installed-package quickstart and design-partner protocol lead with PostgreSQL,
  transaction ownership, and signed webhooks.
- Release notes state that Taskiq, command-idempotency, delegation, and FastMCP remain
  shipped alpha capabilities rather than implying that they are abandoned or stable.
- Schema, roles, forced RLS, identities, route snapshots, and versioned conformance
  evidence remain contractual independently of Python helper maturity.
- Adding another backend, broker, workflow engine, scheduler, or agent integration is
  outside the quarter scope.
- The later public-surface freeze must reconcile any remaining mismatch between this
  matrix and the v1 inventory before beta promotion.

## Follow-up gates

The corrected alpha is FE-020 in the quarter roadmap. Public-surface reconciliation and
the narrow beta freeze occur under FE-030 and FE-039. External partner and independent
review evidence remain separate promotion prerequisites; this decision creates none.

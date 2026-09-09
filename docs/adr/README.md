# Architecture decision records

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-trust-model.md) | Accepted | Fixed trust model and three PostgreSQL roles |
| [0002](0002-explicit-uow-transaction.md) | Accepted | Mergen owns the explicit outer transaction |
| [0003](0003-event-delivery-attempt-model.md) | Accepted | Separate immutable event, delivery, and attempt history |
| [0004](0004-routing-and-policy-snapshots.md) | Accepted | Exact frozen routes and immutable per-delivery policy |
| [0005](0005-relay-state-machine.md) | Accepted | Polling lease relay with token-checked transitions |
| [0006](0006-conformance-evidence.md) | Accepted | Versioned executable conformance evidence |
| [ADR-006](ADR-006-runtime-recovery.md) | Accepted | Truthful cumulative runtime recovery |
| [ADR-007](ADR-007-runtime-public-api.md) | Accepted | Runtime public API and transaction boundary |
| [ADR-008](ADR-008-schema-and-identity.md) | Accepted | Runtime schema and identity rules |
| [ADR-009](ADR-009-roles-and-rls.md) | Accepted | PostgreSQL roles and forced RLS |
| [ADR-010](ADR-010-leases-and-replay.md) | Accepted | Lease fencing and replay identity |
| [ADR-011](ADR-011-taskiq-handoff.md) | Accepted | Durable Taskiq handoff boundary |
| [ADR-012](ADR-012-command-idempotency.md) | Accepted | Transactional command idempotency |
| [ADR-013](ADR-013-delegation.md) | Accepted | Target-bound delegated authority |
| [ADR-014](ADR-014-webhook-retention.md) | Accepted | Tenant-bound bounded webhook retention |
| [ADR-015](ADR-015-control-plane-budgets.md) | Accepted | Bounded control-plane, finalization, and shutdown work |

## Decision rule

An accepted ADR may be superseded, not silently edited into a different decision.
Changes to a frozen invariant require a new ADR, conformance updates, migration impact,
and roadmap re-estimate.

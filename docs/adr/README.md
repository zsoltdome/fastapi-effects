# Architecture decision records

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-trust-model.md) | Accepted | Fixed trust model and three PostgreSQL roles |
| [0002](0002-explicit-uow-transaction.md) | Accepted | Mergen owns the explicit outer transaction |
| [0003](0003-event-delivery-attempt-model.md) | Accepted | Separate immutable event, delivery, and attempt history |
| [0004](0004-routing-and-policy-snapshots.md) | Accepted | Exact frozen routes and immutable per-delivery policy |
| [0005](0005-relay-state-machine.md) | Accepted | Polling lease relay with token-checked transitions |
| [0006](0006-conformance-evidence.md) | Accepted | Versioned executable conformance evidence |

## Decision rule

An accepted ADR may be superseded, not silently edited into a different decision.
Changes to a frozen invariant require a new ADR, conformance updates, migration impact,
and roadmap re-estimate.

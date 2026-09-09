# ADR 015: Bound relay control-plane and shutdown work

- **Status:** Accepted
- **Date:** 2026-09-14

## Decision

Effect execution, database control work, finalization, and process shutdown use
separate budgets. The route snapshot remains authoritative for whether an effect may
execute. `RelayConfig.control_plane_timeout_seconds` bounds each reconcile or claim
session, including pool checkout, transaction completion, rollback, and cooperative
session cleanup. `finalization_timeout_seconds` bounds success/failure persistence and
is reserved only for recording an already-finished effect; it never extends handler,
lease, or total-delivery authority.

`shutdown_grace_seconds` stops new admission, lets the current cycle drain within the
grace, then cancels remaining cooperative work. An unconfirmed finalization is not
retried inline and its lease remains recoverable after expiry. The Taskiq worker uses a
separate control-plane timeout around admission, lookup, and finalization.

PostgreSQL `clock_timestamp()` is sampled after finalization locks. Transaction-frozen
`now()` is not used as proof that a lock-delayed transition remained on time. The
documented persistence boundary is the post-lock validation/state transition; commit
is also subject to the finalization budget. If cancellation races commit, recovery
must inspect durable state and must not assume success or failure.
Application clocks cannot advance, backdate, or extend production lease, command, or
handoff persistence boundaries. Deterministic tests inject an explicit database clock;
the production default always samples PostgreSQL.

## Operational boundary

Async cancellation is cooperative. Pool, connect, statement, and lock timeouts should
also be configured in SQLAlchemy/asyncpg/PostgreSQL below the Mergen operation budget.
CPU-bound or cancellation-suppressing application code cannot be hard-preempted by the
library; after the advertised supervisor grace, process termination belongs to the
service manager. At-least-once recovery and consumer deduplication remain required.

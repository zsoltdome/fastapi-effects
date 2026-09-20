# ADR 0002: Own the explicit outer transaction

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

Ambient sessions, global SQLAlchemy listeners, or a process-global `emit()` obscure
which transaction owns tenant binding and event insertion. Hidden listeners also
widen connection-pool and nesting failure modes.

## Decision

`FastAPIEffectsUnitOfWork` owns the outermost async SQLAlchemy transaction through the MDP.

- Entry rejects an already active session transaction.
- Entry begins explicitly and executes transaction-local tenant binding before
  application SQL.
- `emit()` is available only through the active UoW.
- Nested FastAPI Effects UoWs are rejected.
- Application savepoints after binding are allowed.
- Exit commits once on success, otherwise rolls back.
- Context tokens and session metadata reset in `finally`.
- The first implementation uses no global SQLAlchemy event listener.

## Sequence outcomes

| Path | Transaction result | Context/session result |
|---|---|---|
| Success | One commit | Reset/returned cleanly |
| Application exception | Rollback | Reset; original error propagates |
| Emit/snapshot failure | Rollback all application/effect rows | Reset |
| Commit failure | Report failure; attempt cleanup | Reset; unusable connection discarded by provider |
| Cancellation | Rollback cleanup; cancellation propagates | Reset |
| Dependency finalizer failure | UoW result already explicit | FastAPI Effects context remains reset |

## Consequences

- Integration requires the FastAPI Effects UoW pattern rather than wrapping an arbitrary
  already-open transaction.
- Transaction ownership is testable and narrow.
- Applications needing an existing outer transaction are a post-MDP design problem.

## Rejected alternatives

- global begin listener — hidden lifecycle and pool interaction;
- ambient `ContextVar` session lookup — not an authoritative transaction boundary;
- silently adopting an existing transaction — ambiguous commit responsibility;
- committing inside `emit()` — breaks application atomicity.

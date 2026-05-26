# Boundary Contract v0.1

**Status:** accepted for Milestone 1.  
**Applies to:** the Mergen-owned transition from an authenticated tenant-scoped
application transaction to deferred handler or webhook execution.

The key words **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**, and **DOES NOT** are
normative.

## 1. Boundary

```text
authenticated request
        │ trusted Principal
        ▼
MergenUnitOfWork owns outer transaction
        │ SET LOCAL tenant context before application SQL
        ├── application state
        ├── immutable event
        └── original delivery intents
                 │ commit
                 ▼
          polling relay / sinks
```

Mergen owns neither caller authentication nor remote consumer behavior. It accepts a
trusted `Principal` from the host application and makes transaction, identity,
policy, and delivery state explicit.

## 2. Three primitives

### Principal

An immutable trusted security context containing at least tenant, subject, optional
actor/client, origin scopes, authentication timestamps, and non-secret references.
A `ContextVar` may expose process-local convenience, but durable execution authority
comes from persisted principal and policy snapshots.

### Effect

An immutable typed intent whose event record is persisted in the same local
transaction as the application change. Arbitrary ORM serialization is forbidden.

### Delivery

One independently retryable route from one effect to one destination. A handler and
each webhook subscription have separate delivery rows, status, attempts, retry clock,
and terminal outcome.

## 3. Seven invariants

### BC-01 — Atomic intent

The implementation **MUST** commit the application mutation, event, and every original
delivery intent in one local PostgreSQL transaction, or commit none. It **MUST NOT**
invoke a sink during emission.

Future conformance tests: `C-ATOMIC-COMMIT`, `C-ATOMIC-ROLLBACK`,
`C-EMIT-ACTIVE-UOW`, `C-EMIT-NO-SINK-BEFORE-COMMIT`.

### BC-02 — Tenant continuity

Event, delivery, attempt, execution principal, and tenant-bound handler session
**MUST** identify the same tenant. Composite foreign keys and forced RLS **MUST**
reject cross-tenant references and operations. Missing tenant context **MUST** fail
closed for the request/handler role.

Future tests: `C-RLS-READ`, `C-RLS-WRITE`, `C-RLS-MISSING`, `C-TENANT-FK`,
`C-CONTEXT-LEAK`.

### BC-03 — Explicit authority provenance

Each delivery **MUST** declare exactly one authorization mode: attenuated snapshot,
revalidation under the origin ceiling, or named service policy. User-derived modes
**MUST NOT** expand the origin authority. Service authority **MUST NOT** masquerade as
user authority.

Future tests: `C-AUTH-SNAPSHOT-NO-EXPAND`, `C-AUTH-REVALIDATE-NO-EXPAND`,
`C-AUTH-REVOCATION`, `C-AUTH-SERVICE-EXPLICIT`.

### BC-04 — Stable retry identity

Automatic retry **MUST** retain the same delivery and consumer-visible message ID and
create a new attempt ID/number. The system **DOES NOT** promise that a remote effect is
executed only once.

Future tests: `C-RETRY-STABLE-ID`, `C-ATTEMPT-APPEND`, `C-CRASH-AFTER-EFFECT`.

### BC-05 — Independent fan-out

Each destination **MUST** own independent state, lease, attempts, retry schedule, and
terminal result. Failure or replay of one destination **MUST NOT** mutate a sibling.

Future tests: `C-FANOUT-INDEPENDENT`, `C-SIBLING-FAILURE`, `C-SIBLING-REPLAY`.

### BC-06 — Causal lineage

Event, delivery, attempt, tenant, subject, optional actor/client, correlation,
causation, route version, and valid trace context **MUST** remain linkable. Raw
credentials and plaintext secrets **MUST NOT** be used to achieve lineage.

Future tests: `C-LINEAGE`, `C-TRACE-VALIDATION`, `C-NO-CREDENTIAL-PERSISTENCE`.

### BC-07 — Replay accountability

Manual replay **MUST** create a new delivery ID linked to an immutable original
terminal delivery. The original terminal outcome **MUST NOT** return to pending.
Replay **MUST** record reason and authorizing subject.

Future tests: `C-REPLAY-NEW-ID`, `C-REPLAY-LINEAGE`, `C-TERMINAL-IMMUTABLE`.

## 4. Transaction ownership

For the first implementation, `MergenUnitOfWork` owns the outermost
`AsyncSession` transaction.

- Entry **MUST** reject a session already in a transaction.
- Entry **MUST** bind the tenant before application SQL.
- Nested Mergen UoWs **MUST** be rejected.
- Application savepoints after tenant binding are permitted.
- Exit **MUST** commit once on success or roll back on exception/cancellation.
- Context and session metadata **MUST** reset in `finally`.
- The implementation **MUST NOT** depend on a global SQLAlchemy event listener.

## 5. Delivery contract

- Publication is locally atomic.
- Delivery is at least once.
- A cooperating consumer can obtain an effectively-once outcome by durably
  deduplicating the stable delivery/message ID in the same transaction as its effect.
- Claim transactions are short; handler/network I/O **MUST NOT** occur while claim
  locks are held.
- Finalization and renewal **MUST** compare the exact current lease token.
- Polling is authoritative through Milestone 3.
- Ordering and cancellation are undefined and unsupported.

## 6. Security contract

- Runtime roles **MUST NOT** be superusers, object owners, or hold `BYPASSRLS`.
- Request and handler work uses `mergen_app`; control-plane relay work uses
  `mergen_relay`; DDL uses `mergen_migration_owner`.
- The relay connection **MUST NOT** enter application handler code.
- Raw bearer tokens, cookies, API keys, session tokens, and plaintext webhook secrets
  **MUST NOT** be persisted in Mergen rows or default logs.
- Tenant-supplied webhook endpoints are hostile by default.

## 7. Contract exclusions

The contract **DOES NOT** define generic exactly-once execution, global ordering,
cancellation, workflow compensation, authentication, tenant provisioning, queue
broker semantics, inbound request idempotency, or non-PostgreSQL isolation.

## 8. Change control

A change to any invariant, guarantee, identity rule, role boundary, authorization
formula, route snapshot, or lease transition requires:

1. a new or superseding ADR;
2. an updated conformance mapping;
3. a migration/compatibility impact statement;
4. a roadmap re-estimate before implementation.

# ADR 0003: Separate event, delivery, and attempt

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

One outbox row with a sink array and one status cannot represent an event routed to a
handler and several independently succeeding/failing webhooks. Retry and replay also
need distinct identity and immutable history.

## Decision

Use three tenant-scoped entities:

- **event:** immutable typed intent, principal, payload hash, dedupe, and causal data;
- **delivery:** one immutable route/destination/policy snapshot plus mutable legal
  state, lease, retry, terminal, and replay fields;
- **attempt:** append-only execution history for one claim token/attempt number.

Every relation uses a composite tenant-safe foreign key. Original deliveries are
unique per event/route version/destination key. Automatic retry retains delivery ID;
manual replay creates a new delivery linked through `replay_of`.

Emission dedupe is `(tenant_id, namespace, key)`. A hit is compatible only when event
type, schema version, and canonical payload hash match. A compatible hit uses the
first event and original route snapshots; a mismatch raises `DedupeConflict`.

## Immutable fields

After commit, event principal/payload/type/causality and delivery route/destination/
policy snapshots cannot change. Terminal status/time and original replay lineage are
not reopened or rewritten. Retention may delete eligible history in dependency order
but not mutate its meaning.

## Consequences

- Fan-out state is correct but uses more rows.
- Manual replay is auditable and intentionally receives new consumer identity.
- Migrations and repository methods must preserve partial unique indexes and check
  constraints, not only ORM validation.

## Rejected alternatives

- sink array on event/outbox row — cannot model independent outcomes;
- mutable route lookup on retry — changes committed intent;
- resetting dead delivery to pending — rewrites terminal history;
- dedupe by payload alone — insufficient command namespace and collision semantics.

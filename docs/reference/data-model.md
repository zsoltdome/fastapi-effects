# Event, delivery, and attempt model

This is the normative logical model implemented by schema revision `core=1`.

## Event

An event owns:

- UUID identity and tenant ID;
- principal subject, actor/client, origin scopes, approved opaque credential reference,
  and authentication timestamps;
- event type, positive schema version, typed JSON payload, canonical SHA-256 hash;
- optional tenant-scoped dedupe namespace/key;
- correlation, causation, and trace context;
- occurred and database-created timestamps.

Constraints:

- unique `(tenant_id, event_id)` supports tenant-safe composite references;
- partial unique `(tenant_id, dedupe_namespace, dedupe_key)` when a key exists;
- namespace/key are both null or both present;
- payload and scope counts are bounded;
- event rows are immutable after commit except retention deletion.

A compatible dedupe hit requires the same tenant, event type, schema version, and
payload hash. It returns the first event and route snapshots. A mismatch raises
`DedupeConflict` without including payload content.

## Delivery

A delivery owns:

- UUID identity, tenant-safe event reference, optional replay reference;
- route key/version and snapshot schema version;
- sink kind, stable destination key, immutable destination snapshot;
- immutable authorization and retry policy snapshot;
- state, attempts started, and next-attempt time;
- current lease token/expiry only while leased;
- replay reason and authorizing subject;
- creation and update timestamps.

The unique original-route key prevents duplicate original delivery materialization.
Lease and terminal check constraints reject impossible combinations.

## Delivery attempt

An attempt owns:

- UUID identity and tenant-safe delivery reference;
- positive attempt number and lease token;
- start/finish and outcome;
- a bounded failure code and safe summary for failed attempts.

`(tenant_id, delivery_id, attempt_number)` is unique. Payloads, policy bodies,
credentials, secrets, and receiver response bodies are not attempt columns.

## Tenant-safe references

Every relation includes tenant ID:

```text
(tenant_id, event_id)    → events(tenant_id, event_id)
(tenant_id, delivery_id) → deliveries(tenant_id, delivery_id)
(tenant_id, replay_of)   → deliveries(tenant_id, delivery_id)
```

This prevents a direct-SQL or ORM bug from linking history across tenants even when a
UUID from another tenant is known.

## Immutability

After commit, event payload/principal/causality and delivery route/destination/policy
snapshots are not updated. Runtime state fields on delivery change only through legal
state-machine transitions. Attempts are append-only except bounded completion of the
same attempt and reconciliation of an unfinished attempt to `abandoned`/`lease_lost`.

## Retention

Initial planned defaults are 30 days for attempts and succeeded deliveries, 90 days
for dead deliveries, and event retention while referenced. Purge order is attempts,
deliveries, then unreferenced events, in bounded batches. Retention deletes history;
it never rewrites a terminal result.

# Event, delivery, and attempt model

This is the normative logical model; SQLAlchemy mappings and migrations begin in
Milestone 2.

## Event

An event owns:

- UUID identity and tenant ID;
- principal schema/version, subject, actor/client, origin scopes, approved metadata,
  and authentication timestamps;
- event type, positive schema version, typed JSON payload, canonical SHA-256 hash;
- optional tenant-scoped dedupe namespace/key;
- correlation, causation, and trace context;
- occurred and database-created timestamps.

Constraints:

- unique `(id, tenant_id)` supports tenant-safe composite references;
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
- status, attempts started, max attempts, next-attempt time, deadline;
- current lease worker/token/expiry only while leased;
- first attempt, terminal time, bounded last error;
- replay reason and authorizing subject;
- state version and timestamps.

The unique original-route key prevents duplicate original delivery materialization.
Lease and terminal check constraints reject impossible combinations.

## Delivery attempt

An attempt owns:

- UUID identity and tenant-safe delivery reference;
- positive attempt number, lease token, worker ID;
- start/finish and outcome;
- bounded transport metadata such as status, duration, byte counts, request ID, and
  retry-after time;
- bounded error class/code/summary.

`(delivery_id, attempt_no)` is unique. The payload, policy body, credentials, secrets,
and webhook response body are not attempt columns.

## Tenant-safe references

Every relation includes tenant ID:

```text
(event_id, tenant_id)    → event(id, tenant_id)
(delivery_id, tenant_id) → delivery(id, tenant_id)
(replay_of, tenant_id)   → delivery(id, tenant_id)
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

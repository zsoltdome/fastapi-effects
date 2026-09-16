# Retries, dead-letter state, and replay

## Retry profile

A versioned immutable retry snapshot contains:

```text
max_attempts
maximum_elapsed_seconds
base_delay_seconds
maximum_delay_seconds
jitter = full
handler_timeout_seconds
lease_duration_seconds
```

- `attempt_count` counts attempts started at claim.
- Full-jitter exponential backoff uses injected randomness in tests.
- Persisted scheduling uses database time.
- `maximum_elapsed_seconds` defines a latest-finish deadline at
  `delivery.created_at + maximum_elapsed_seconds`.
- `Retry-After` may increase a delay but never schedules work at or beyond that
  delivery deadline.
- Claim, reconciliation, handler/webhook execution, and external-executor admission
  all enforce the same absolute deadline. An attempt is also bounded by its handler
  timeout and current lease expiry.

## Default classification

Retryable:

- transient database/control-plane failures;
- handler timeout or unknown handler exception within limits;
- temporary authorization-provider outage;
- transient DNS/connect/reset/HTTP server behavior for webhooks.

Terminal:

- explicit `PermanentDeliveryError`;
- authorization expiry or denial under the declared policy;
- unsupported event/route/policy schema;
- blocked destination or invalid TLS identity;
- exhausted attempts or deadline.

Only bounded, sanitized error class/code/summary is persisted. Error stack locals,
payloads, tokens, and response bodies are not attempt fields.

## Automatic retry

Automatic retry preserves:

- event ID;
- delivery/message ID;
- route and destination snapshots;
- policy snapshot;
- replay lineage.

It creates a new attempt ID, number, lease token, timestamps, and outcome.

## Dead-letter state

A delivery becomes `dead` when failure is terminal or retry/deadline bounds are
exhausted. Dead is immutable for the original row. Operators inspect the event,
snapshot, and bounded attempts before choosing a new replay.

## Manual replay

Replay creates a new delivery row with:

- a new delivery and consumer-visible message ID;
- `replay_of` pointing to the original tenant-safe delivery identity;
- copied event, route, destination, and policy snapshots by default;
- explicit reason and authorizing subject;
- fresh attempt history.

A privileged replay policy may allow selected policy fields to be refreshed, but the
change is explicit and audited. The original terminal delivery is never edited back
to pending. A replay starts a fresh elapsed-time budget from the new delivery's
creation time without changing the original delivery's budget or history.

Ordinary replay also copies the original webhook route and secret-set snapshot. If all
keys eligible under that snapshot are revoked or expired, replay remains unsignable.
Pausing/reactivating a subscription, rotating another active set, or updating the
subscription for future events does not retarget historical work. Any future explicit
re-key/retarget operation requires its own authorization, audit, and immutable-lineage
design; it is not part of ordinary replay.

Webhook replay and webhook retention take the same tenant-scoped transaction advisory
lock. If replay wins, pruning observes and preserves the original lineage root; if
retention commits first, a later replay fails cleanly because the terminal source no
longer exists. This serialization avoids a foreign-key race without granting the
application role row-update authority.

## Receiver deduplication

An at-least-once receiver should place a unique constraint on the stable message ID
and record it in the same transaction as the business effect. Duplicate automatic
attempts return a success-compatible response without repeating the effect. A manual
replay has a new message ID and is intentionally eligible to run again.

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
- `Retry-After` may increase a delay but is clamped by policy and delivery deadline.
- No attempt starts after maximum elapsed time or an explicit deadline.

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
to pending.

## Receiver deduplication

An at-least-once receiver should place a unique constraint on the stable message ID
and record it in the same transaction as the business effect. Duplicate automatic
attempts return a success-compatible response without repeating the effect. A manual
replay has a new message ID and is intentionally eligible to run again.

# Webhook operations

Install `fastapi-mergen[webhooks]`, apply Alembic through `0002_webhooks`, and
configure the application and relay roles described in the role runbook.
Subscription create/update/pause/reactivate and key operations require a tenant
principal with `webhooks:manage` (or the restricted `mergen:operator` scope).

Only exact event types are supported. `emit()` reads active subscription heads
inside the business transaction and snapshots the current immutable version into
the delivery. Pausing or editing a subscription changes future events only; it
does not cancel already committed delivery intent.

The production endpoint policy requires HTTPS on port 443, rejects credentials
and fragments, normalizes IDNA hostnames, and re-resolves DNS for every attempt.
Every answer must be global unicast. The connection is then made to one approved
IP while TLS certificate verification, SNI, and the HTTP Host header retain the
original hostname. Redirects are terminal by default.

Response bodies are drained only up to configured limits and are discarded.
2xx succeeds; 408, 425, 429, 5xx and transient transport failures retry. Other
responses are terminal. `Retry-After` is clamped by both route policy and the
delivery deadline.

## Runbook

- Inspect dead deliveries and their bounded failure codes; receiver response
  content is deliberately unavailable.
- Fix the receiver, then use manual replay. Replay creates a new delivery and
  `webhook-id` linked to the terminal original.
- Persistent failures increment a streak. Threshold crossing auto-pauses future
  snapshotting and emits one audit record; committed deliveries remain active.
- Treat receiver success followed by relay crash as ambiguous. The retry uses the
  same message ID, so receivers must enforce a unique message-ID boundary.
- Run bounded retention after the audit period. Attempts are removed before
  terminal deliveries, then unreferenced events and expired key versions.
- Diagnose DNS policy, TLS hostname, certificate-chain, timeout, and response
  bound failures separately; never weaken address policy to make a receiver work.

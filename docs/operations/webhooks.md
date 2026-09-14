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
Unicode path and query text is UTF-8 percent-encoded once into an ASCII URI; valid
existing percent escapes and reserved delimiters retain their spelling, while malformed
escapes, lone surrogates, control characters, spaces, and fragments are rejected.
Create/update validation returns a configuration error. The attempt path converts an
invalid older snapshot or remote redirect target into terminal
`webhook.endpoint_invalid` for that delivery, without logging the URL.
Every answer must be global unicast. The connection is then made to one approved
IP while TLS certificate verification, SNI, and the HTTP Host header retain the
original hostname. Production rejects supplied TLS contexts that disable certificate
or hostname verification or permit protocols below TLS 1.2; custom CA contexts remain
supported when those controls stay enabled. Redirects are terminal by default.

One aggregate attempt deadline covers signing-key lookup, DNS, the bounded address
set (eight by default), redirects, request/response I/O, and connection cleanup. A
mutable TLS context is revalidated immediately before I/O. Informational HTTP/1.1
responses are consumed under shared count/header/time budgets until a final response;
protocol upgrade (`101`) is unsupported and terminal.

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

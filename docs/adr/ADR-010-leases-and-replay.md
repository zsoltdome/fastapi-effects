# ADR-010: Leases, retries, and replay

- Status: Accepted
- Date: 2026-08-30

Claims use short `FOR UPDATE SKIP LOCKED` transactions. A claim creates a fresh opaque
lease token and append-only started attempt, then commits before handler, broker, DNS,
TLS, or HTTP I/O. Finalization compares both leased state and token. A stale worker may
record lease loss but cannot overwrite reclaimed work.

Retry scheduling uses the delivery's frozen full-jitter policy. Expired leases abandon
the open attempt and make the stable delivery identity reclaimable. Polling is the
correctness path; notification is only a wake-up hint.

Manual replay never mutates a terminal delivery. It creates a new linked delivery and
message identity with an auditable actor and reason.

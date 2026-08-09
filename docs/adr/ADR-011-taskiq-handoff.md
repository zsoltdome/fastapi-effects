# ADR-011: Durable Taskiq handoff

Status: accepted

## Decision

Mergen owns delivery attempts, retry timing, and terminal state. Taskiq owns only
broker transport and worker invocation. A broker acknowledgement changes a durable
handoff from `prepared` to `enqueued`; it never completes the Mergen delivery.

Each delivery attempt has at most one handoff, a stable `mergen-<attempt UUID>`
Taskiq ID, and an opaque handoff token. A worker atomically moves `prepared` or
`enqueued` work to `executing` with a unique execution token and deadline.
Completion is a compare-and-set on that token and finalizes the parent delivery
attempt in the same PostgreSQL transaction.

The states are `prepared`, `enqueued`, `executing`, `succeeded`, `retry_wait`, and
`dead`. Prepared state is committed before broker I/O. A worker may legitimately
observe a message before the sender records its acknowledgement; receipt itself
therefore permits `prepared → executing` and records `enqueued_at`. Cancellation
during enqueue remains ambiguous and is resolved by either that worker or bounded
recovery.

The broker envelope contains only version, tenant, handoff, delivery, attempt,
stable task ID, and opaque handoff token. Sessions, database credentials, original
bearer credentials, cookies, secrets, payloads, and Python callables are forbidden.
The worker reloads the durable event, route, and principal and executes through the
same handler executor and fresh tenant application-session provider as the polling
relay.

Taskiq retry middleware is not application retry authority and must be disabled for
the bridge task. Duplicate broker messages are expected; only one execution token
may be active. Expired work is finalized into Mergen retry/dead policy. External
effects remain at least once and handlers must use the stable delivery identity for
their own deduplication.

# Relay state and operation

**Status:** implemented core runtime behavior in `0.7.0a1`.

## State machine

```text
pending ──claim──▶ leased ──success────────────▶ succeeded
                       │
                       ├─retryable failure──────▶ retry_wait ──claim──▶ leased
                       │
                       ├─terminal failure───────▶ dead
                       │
                       └─lease expires──────────▶ reclaimable by new token
```

Terminal rows never return to pending. Manual replay creates a new linked delivery.

## Claim transaction

At PostgreSQL `READ COMMITTED`, a worker:

1. ranks due deliveries per tenant, then locks a bounded set with
   `FOR UPDATE SKIP LOCKED`;
2. assigns `state='leased'`, a fresh random lease token, and an expiry from the
   injected runtime clock;
3. increments attempts started and sets first-attempt time when absent;
4. inserts one append-only attempt row with the same token and attempt number;
5. commits immediately;
6. executes no handler, authorization provider, DNS, signing, or network operation
   while row locks are held.

The claim API returns immutable snapshots detached from the ORM session. It cannot
accept a sink callback, making I/O inside the lock transaction structurally difficult.

## Bounded tenant fairness

The MDP promises bounded unfairness, not ordering:

1. rank due rows within each tenant by due time and creation time;
2. retain at most `per_tenant` rows from each rank partition;
3. order the bounded candidates by due age;
4. stop at `batch_size`; and
5. use `SKIP LOCKED` only to coordinate competing workers.

No FIFO, global, causal, or per-key ordering SLA is implied.

## Execution

A claimed worker:

- reads immutable event, route, destination, retry, and authorization snapshots;
- reconstructs or revalidates authority;
- binds process-local principal context for the attempt;
- obtains a fresh tenant-bound `mergen_app` session for an internal handler;
- invokes exactly one sink outside the claim transaction;
- renews a lease only through token-checked compare-and-set;
- applies timeout, payload, and concurrency limits.

The `mergen_relay` control-plane session is never exposed through `EffectContext`, a
handler dependency, or an application session provider.

## Finalization

Every delivery update requires:

```text
id = claimed_delivery_id
AND status = 'leased'
AND lease_token = claimed_lease_token
```

Success, retryable failure, and terminal failure update the current attempt and
delivery in one short transaction. A stale-token mismatch changes no current delivery
state and produces a `LeaseLost` result and metric.

Lease loss during either success or failure finalization is a per-delivery race. The
relay records it without cancelling sibling deliveries, and transient SQLAlchemy
connection failures leave committed leases for normal expiry/reconciliation while the
supervisor continues polling. Mergen configuration/invariant errors and explicit
shutdown cancellation still propagate.

## Lease expiry and reconciliation

The bounded reconciliation pass changes an expired lease to `retry_wait` (or `dead`
when its attempt or latest-finish budget is exhausted) and marks its open attempt
`abandoned`. A later claim uses a new token and attempt identity. A stale process
cannot finalize either the reconciled row or its replacement lease.

## Polling

Periodic polling is the correctness path through v1. A later
`LISTEN/NOTIFY` integration may reduce latency only as a wake-up hint; polling remains
enabled and recovers missed notifications.

## Graceful shutdown

1. stop selecting tenants;
2. stop new claims;
3. wait for active work through a bounded grace period;
4. renew only work deliberately permitted to finish;
5. otherwise cancel local execution and let the lease expire;
6. close sessions and reset contexts;
7. exit non-zero on an internal invariant failure.

`RelayConfig` separates the effect deadline from
`control_plane_timeout_seconds`, `finalization_timeout_seconds`, and
`shutdown_grace_seconds`. Database acquisition, statements, transaction completion,
rollback, and cooperative session cleanup are inside the applicable control budget.
Finalization allowance records an already-finished effect and never authorizes more
effect execution. A timeout or ambiguous commit leaves the fenced lease for inspection
and expiry recovery; it is not blindly replayed inline. See ADR-015.

The CLI installs explicit SIGTERM and SIGINT handlers on platforms that support event
loop signal handlers. Cancellation is cooperative; the process supervisor owns hard
termination of CPU-bound or cancellation-suppressing application code after its own
deadline.

## Operational signals

Required bounded-cardinality metrics include due age, claims, active work, outcome,
retry, dead rows, lease loss, renewals, abandoned attempts, and loop failures. Payloads,
raw scopes, policy bodies, credentials, and secrets are excluded by default.

# Relay state and operation

**Status:** normative design; implementation begins in Milestone 2.

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

1. selects a bounded tenant and due deliveries with `FOR UPDATE SKIP LOCKED`;
2. assigns `status='leased'`, worker ID, fresh random lease token, and database-time
   lease expiry;
3. increments attempts started and sets first-attempt time when absent;
4. inserts one append-only attempt row with the same token and attempt number;
5. commits immediately;
6. executes no handler, authorization provider, DNS, signing, or network operation
   while row locks are held.

The claim API returns immutable snapshots detached from the ORM session. It cannot
accept a sink callback, making I/O inside the lock transaction structurally difficult.

## Bounded tenant fairness

The MDP promises bounded unfairness, not ordering:

1. select a bounded tenant set ordered by oldest due delivery;
2. rotate the starting tenant between loops;
3. claim at most `per_tenant_claim_limit` rows per tenant;
4. stop at the worker batch limit;
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

## Lease expiry and reconciliation

A new claim may reclaim an expired lease with a new token and attempt number. The
prior unfinished attempt becomes `abandoned` exactly once through a bounded
reconciliation transaction. A stale process cannot renew or finalize the replacement
worker's lease.

## Polling

Periodic polling is the correctness path through Milestone 3. A later
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

## Operational signals

Required bounded-cardinality metrics include due age, claims, active work, outcome,
retry, dead rows, lease loss, renewals, abandoned attempts, and loop failures. Payloads,
raw scopes, policy bodies, credentials, and secrets are excluded by default.

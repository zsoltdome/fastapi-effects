# ADR 0005: Use a polling lease state machine

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

Distributed workers can crash before execution, during an effect, after remote
success, during heartbeat, or before finalization. Holding database locks during
network or handler work harms concurrency and does not remove ambiguous remote
success.

## Decision

Use states `pending`, `leased`, `retry_wait`, `succeeded`, and `dead`.

Claim in a short `READ COMMITTED` transaction using `FOR UPDATE SKIP LOCKED`; create a
fresh lease token; increment attempts started; insert the attempt; commit before I/O.
Renewal and finalization require delivery ID, `leased` state, and exact token.
Expired work is reclaimable with a new token/attempt; the old unfinished attempt is
reconciled to `abandoned`. Polling is authoritative. Tenant fairness is bounded, not
strict ordering.

## Kill-point matrix

| Kill point | Durable state | Recovery expectation |
|---|---|---|
| Before application commit | Nothing | No delivery exists |
| After commit, before claim | Pending delivery | Poller claims it |
| During claim before commit | Prior state | Transaction rollback; claim again |
| After claim, before execution | Leased + started attempt | Lease expires; new attempt |
| During handler/network effect | Ambiguous | Lease expires; same delivery ID retried |
| After remote success, before finalization | Remote effect + leased row | Duplicate same message ID; consumer dedupe required |
| During renewal before commit | Prior lease expiry | Retry renewal or reclaim after expiry |
| After replacement claim, stale finalization | New token current | Stale update rejected; no current-state mutation |
| During shutdown | Claims stopped first | Finish within grace or let lease expire |

## Retry rules

Use full-jitter exponential backoff, max attempts, maximum elapsed time, deadlines,
timeouts, and lease duration from immutable policy. Database time is authoritative for
persisted scheduling. `Retry-After` is bounded by policy/deadline.

## Consequences

- Delivery is at least once; duplicates are explicit.
- Claim throughput is scalable without long-held locks.
- Consumers that require one effect must deduplicate stable message identity.
- A future notification mechanism can only wake pollers; it does not replace polling.

## Rejected alternatives

- execute while holding row lock — poor concurrency and still ambiguous remote result;
- status-only ownership — stale worker can overwrite replacement;
- exactly-once marketing claim — not supportable across external systems;
- strict global fairness/order — out of MDP and expensive to guarantee.

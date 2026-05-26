# Guarantee vocabulary

This document fixes terms used by source, tests, documentation, and product claims.

## Guarantee table

| Boundary | Guarantee | Explicit non-guarantee | Conformance IDs |
|---|---|---|---|
| Application rows + event + original deliveries | Atomic local commit | No atomicity with remote systems | `C-ATOMIC-COMMIT`, `C-ATOMIC-ROLLBACK` |
| Rolled-back application transaction | No committed event or original delivery | No attempt to compensate an effect fired outside Mergen | `C-ATOMIC-ROLLBACK` |
| Delivery execution | At least once | No generic exactly-once execution | `C-CRASH-AFTER-EFFECT` |
| Consumer-visible outcome | Effectively once only with durable consumer deduplication | Sender cannot prove remote effect after an ambiguous crash | `C-CONSUMER-DEDUPE` |
| Fan-out | Independent status and retry history per destination | No all-destinations distributed transaction | `C-FANOUT-INDEPENDENT` |
| Automatic retry | Same delivery/message ID; new attempt ID | No new business intent | `C-RETRY-STABLE-ID` |
| Manual replay | New delivery/message ID linked to original | Original terminal row is not reopened | `C-REPLAY-NEW-ID` |
| Ordering | None | No FIFO, causal, per-tenant, or per-key ordering | Documentation-only until ordering is admitted |
| Cancellation | Undefined | No promise that pending/in-flight work can be cancelled | Documentation-only until cancellation is admitted |
| Notification | Polling is authoritative | Notification does not prove durable work exists | `C-POLLING-RECOVERY` |

Recommended public wording:

> **Atomic publication, at-least-once delivery, and stable identities for
> effectively-once consumers.**

## Atomic publication

An application transaction is complete only when all of the following are durable:

1. application state;
2. one immutable event;
3. every original delivery selected from the frozen route/subscription snapshot.

A failure in payload validation, route resolution, snapshot construction, dedupe,
insert, flush, or commit rolls back all of them.

## Ambiguous remote success

A relay can send a request, the receiver can commit its effect, and the relay can
crash before recording success. On recovery, the sender cannot distinguish success
from loss and therefore retries the same stable message identity.

```text
send message D
receiver commits effect D
relay crashes before finalization
retry message D
receiver unique(D) suppresses second effect
```

This is documented duplicate delivery with one cooperating-consumer outcome—not a
sender-side exactly-once guarantee.

## Attempt accounting

`attempt_count` means attempts **started**. Claiming a delivery and inserting the
append-only attempt row occur in one transaction. A process crash may leave an
unfinished attempt that is later marked `abandoned`; it does not erase the attempt.

## Dedupe versus replay

Emission dedupe prevents a concurrent command from creating a second event and a new
original route snapshot. A compatible hit returns the first event/deliveries; a
payload/type/version mismatch raises `DedupeConflict`.

Replay is intentional new execution. It has a new delivery/message ID, preserves
lineage through `replay_of`, and records reason and authorizing subject.

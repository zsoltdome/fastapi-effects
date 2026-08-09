# External executor boundary

`TaskiqDeliverySink` is a polling-relay destination. It commits a prepared handoff,
performs broker I/O with no claim locks held, records broker acknowledgement, and
returns `SinkDisposition.DEFERRED`. The relay therefore leaves completion to the
worker rather than marking the delivery successful.

`TaskiqWorkerBridge` validates the strict envelope, claims an execution token in a
short relay transaction, then invokes a configured `HandoffExecutor`. The standard
`HandlerExecutor` reconstructs the principal, applies the snapshotted authorization
mode, binds process context, and exposes only fresh tenant-bound application
sessions. It never passes the relay, request, or broker session into handler code.

Worker success or classified failure fences on both handoff execution token and
parent delivery lease token. Stale workers cannot overwrite recovery or a newer
attempt. `TaskiqRecovery` handles bounded batches of old prepared/enqueued records
and expired executions. Automatic retry creates a new Mergen attempt and therefore
a new handoff/Taskiq ID while retaining event and delivery identity.

# Retention

Retention is explicit, bounded, and dependency ordered. Never delete pending, leased, or
retry-wait work. For terminal webhook history, delete finished attempts first, then
terminal deliveries with no attempts, then orphan events; prune only retiring/revoked
secret versions. Command pruning deletes expired terminal generations through the
security-definer function in bounded batches; relay has execute permission but no direct
table delete permission. Taskiq handoffs remain protected by delivery/attempt foreign
keys until a future independently reviewed handoff-retention operation exists.

Each webhook retention call emits a bounded `webhook_pruned` observation containing only
the destination kind and aggregate pruned-row count. Telemetry failures are isolated from
the pruning transaction and cannot turn a successful or failed batch into the opposite
result.

Choose a cutoff longer than the maximum retry/replay, incident, audit, and consumer
dedupe windows. Re-run a small batch until it returns zero, emit the pruned count, and
observe foreground latency, locks, dead tuples, index bytes, autovacuum, and oldest open
transaction. Operations are resumable because each committed batch is independently
eligible and dependency safe.

The repository rehearsal seeds 1,000 terminal webhook histories alongside pending and
cross-tenant controls, then prunes in independently committed batches of 128 on
PostgreSQL 16 and 18. It verifies the attempts → deliveries → events → revoked-secret
dependency order, preserves active work and active keys, rejects cross-tenant calls, and
matches every post-commit observation to its aggregate deleted-row count.

Before changing a cutoff, take and verify a backup. During a dead-letter surge, key
compromise, suspected replay misuse, failed migration, legal hold, or active incident,
pause pruning. A retention result is not evidence that a remote consumer deleted its
copy, nor does deletion make a duplicate external side effect impossible.

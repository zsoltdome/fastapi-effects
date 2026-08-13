# Production observability

Observability is an optional, best-effort side channel. `NoOpEventSink` is the default;
telemetry backend failures are swallowed and cannot commit, roll back, retry, or finalize
runtime work. Install `fastapi-mergen[otel]` and pass `create_otel_sink()` to stores,
leases, command storage, webhook operations, or Taskiq bridges.

The stable counter is `fastapi_mergen.runtime.events`, labelled by event kind and a small
allowlist of capability, destination kind, outcome, state, authorization result, and
pause status. `fastapi_mergen.operation.duration` is an optional millisecond histogram.
`fastapi_mergen.backlog.oldest_age` is a seconds histogram populated by the read-only
`observe_backlog()` PostgreSQL probe; run it on the operator's chosen interval.
Tenant, subject, event, delivery, attempt, handoff, command, and delegation identifiers
are never metric labels. Lineage identifiers are trace-only; the structured JSON sink
records bounded lineage for incident correlation.

The event vocabulary covers publish, claim, attempt, retry, success, dead, lease loss,
reconcile, replay, webhook/pause/key change, Taskiq prepare/enqueue/execute, command
start/complete/replay/conflict/prune, and delegation issue/allow/deny. Event trace lineage
links the request trace parent to event, delivery, attempt, replay origin, handoff,
command, and delegation identifiers where the capability owns them.

Never place payloads, bodies, credentials, cookies, authorization values, secrets,
tenant/subject IDs, URLs, or exception messages in attributes. The runtime enforces an
exact attribute-name allowlist and size/type limits. Application failure codes must be
stable classifications rather than interpolated user data.

Import `DelegationTelemetrySink` from `fastapi_mergen.observability.delegation` to adapt
token-free delegation audit events. Keep the primary durable audit sink as well when
policy requires it; metrics are not an audit log.

Start with the example dashboard and alerts. Page on sustained oldest-backlog age, dead
rate, lease reconciliation, endpoint pauses, command conflicts, and delegation denials;
ticket on isolated failures. Tune durations from the benchmark and normal traffic. Avoid
alerting on raw row counts without age and rate context.

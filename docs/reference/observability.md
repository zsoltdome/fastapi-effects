# Observability contract

The base runtime emits a bounded vendor-neutral event vocabulary through `EventSink`.
The default sink is a no-op and imports no telemetry dependency. The `otel` extra maps
the same fields to OpenTelemetry.

Events cover publish, claim, attempt, retry, success, dead-letter, lease loss,
reconciliation, and replay. Attributes never include payload/body content, credentials,
secrets, URLs containing user information, or exception text. Tenant identifiers are
not metric labels by default. Trace context is carried only through the validated,
bounded event fields.

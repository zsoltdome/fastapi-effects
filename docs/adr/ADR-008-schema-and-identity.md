# ADR-008: Schema and identity

- Status: Accepted
- Date: 2026-08-30

All durable objects use the `fastapi_effects` schema. Tenant-owned relationships use
composite keys containing `tenant_id`. Events are immutable origin intent; deliveries
are independently retryable destination intent; attempts are append-only observations.

Payload identity is SHA-256 over format-tagged canonical JSON v1 bytes. Event dedupe is
tenant + namespace + bounded key. A compatible duplicate returns the first event and
its original snapshot set; a type, version, or payload mismatch raises
`DedupeConflict`. UUIDs are opaque and do not promise order.

Automatic retry retains delivery/message identity and creates a new attempt. Manual
replay creates a new delivery linked by `replay_of`. Package version and schema revision
are separate identities; startup checks compatibility and never auto-migrates.

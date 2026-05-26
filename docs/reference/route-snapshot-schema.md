# Route and policy snapshot schema

A delivery must be executable without consulting mutable route definitions or
subscription state. Snapshots contain data only—never callables, raw credentials, or
plaintext secrets.

## Handler destination snapshot v1

```json
{
  "schema": 1,
  "handler_key": "invoice.render_pdf",
  "handler_version": 1
}
```

Required properties:

- `schema`: positive snapshot schema revision;
- `handler_key`: stable registered key, not a Python function name inferred at retry;
- `handler_version`: positive supported handler contract version.

## Webhook destination snapshot v1

```json
{
  "schema": 1,
  "subscription_id": "7c8f5fb2-70a9-43d7-a21b-3fbd35dba842",
  "endpoint_url": "https://customer.example/hooks",
  "secret_set_id": "b1169f22-a7fa-45d3-a3e6-0c437846b138"
}
```

The stable secret-set ID permits rotation; no secret or key material appears in the
snapshot. Later endpoint, filter, status, or secret-version changes do not mutate an
existing delivery.

## Policy snapshot v1

```json
{
  "schema": 1,
  "authorization": "revalidate",
  "required_scopes": ["invoices:read"],
  "origin_scope_ceiling": ["invoices:read", "invoices:write"],
  "service_policy": null,
  "maximum_snapshot_age_seconds": null,
  "retry_policy": {
    "name": "default-handler",
    "version": 1,
    "max_attempts": 8,
    "maximum_elapsed_seconds": 86400,
    "base_delay_seconds": 2,
    "maximum_delay_seconds": 900,
    "handler_timeout_seconds": 60,
    "lease_duration_seconds": 120,
    "jitter": "full"
  }
}
```

Rules:

- scope arrays are validated, deduplicated, and serialized deterministically;
- mode-specific fields are required/rejected explicitly;
- resolved retry values are stored, not only a mutable profile name;
- route and retry versions are positive;
- unknown schema revisions dead-letter with `SchemaRevisionMismatch` rather than being
  guessed;
- no arbitrary extension field is trusted for authorization.

## Registry freeze

Routes register before startup completes. The registry validates handlers, retry
profiles, authorization resolvers, and named service policies, then freezes. Exact
event-type matching returns a deterministic route order. Duplicate route key/version,
registration after freeze, or unresolved service policy fails startup.

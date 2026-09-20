# Failure taxonomy

Public failures are typed so retry, terminal, configuration, and conflict behavior do
not depend on exception-message parsing.

| Failure | Category | Default behavior | Sensitive data policy |
|---|---|---|---|
| `FastAPIEffectsConfigurationError` | Startup/configuration | Fail startup/command | Names and safe codes only |
| `MilestoneNotImplementedError` | Pre-alpha safety gate | Fail before operation | No payload/session details |
| `DedupeConflict` | Command conflict | Roll back caller transaction | Tenant/namespace/key may be redacted; no payload |
| `AuthorizationExpired` | Terminal delivery | Dead | Subject/route may be approved identifiers; no token |
| `AuthorizationDenied` | Terminal delivery | Dead | Required/effective scope counts; no raw token |
| `RetryableDeliveryError` | Retryable delivery | Retry within snapshot policy | Bounded class/code/summary |
| `PermanentDeliveryError` | Terminal delivery | Dead immediately | Bounded class/code/summary |
| `LeaseLost` | Concurrency result | Do not mutate current delivery | Delivery/attempt/worker IDs only |
| `SchemaRevisionMismatch` | Terminal compatibility | Dead and alert | Expected/actual integer revisions |

Unknown handler exceptions are retryable until immutable policy limits are exhausted.
Programming/configuration failures discovered at startup should not be deferred into
runtime retries.

The following boundary matrix is normative for the focused 2026-09-20 remediation:

| Condition | Scope | Outcome |
|---|---|---|
| Snapshotted webhook secret set has no active or unexpired retiring key | One delivery | `webhook.no_eligible_signing_key`, terminal without DNS or network I/O |
| Master-key provider is missing, cannot supply a referenced key, or cannot decrypt material | Process/configuration | `FastAPIEffectsConfigurationError` remains visible |
| Reviewed raw refusal/reset/timeout or temporary DNS error while opening a database control connection | One polling cycle | Bounded control failure; a later cycle reconnects |
| Authentication, permission, schema, integrity, certificate, DSN, or permanent name error | Process/configuration | Remains visible; not silently retried |

Raw operating-system errors are accepted only by the database-owned connection/control
boundary. The general delivery/handler classifier deliberately does not treat arbitrary
`OSError` as a database outage.

Exception string/repr behavior must not include payloads, credentials, secrets, full
URLs with query strings, response bodies, SQL parameter values, or stack locals.

# Failure taxonomy

Public failures are typed so retry, terminal, configuration, and conflict behavior do
not depend on exception-message parsing.

| Failure | Category | Default behavior | Sensitive data policy |
|---|---|---|---|
| `MergenConfigurationError` | Startup/configuration | Fail startup/command | Names and safe codes only |
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

Exception string/repr behavior must not include payloads, credentials, secrets, full
URLs with query strings, response bodies, SQL parameter values, or stack locals.

# Numeric configuration domains

This inventory records the reviewed runtime numeric inputs for the corrected alpha.
It distinguishes different domains instead of applying one generic validator.

| Surface | Accepted domain | Invalid classes checked | Review result |
| --- | --- | --- | --- |
| `RelayConfig.poll_interval_seconds` | finite `int` or `float` in `(0, 60]` | booleans, nonnumeric values, NaN, infinities, nonpositive values, oversized integers, above maximum | Confirmed defect fixed |
| Relay control-plane, finalization, and shutdown budgets | finite `int` or `float` in `(0, 300]` | same matrix as polling | Confirmed defect fixed |
| `RetryPolicy` version, attempt count, and maximum elapsed time | positive integers; booleans excluded | non-integers, booleans, nonpositive values | Already fail-closed |
| `RetryPolicy.base_delay_seconds` | finite number greater than or equal to zero | booleans, nonnumeric values, NaN, infinities, negative values | Already fail-closed; zero is intentional |
| Other `RetryPolicy` delay, timeout, and lease values | finite numbers constrained by elapsed-time and lease relationships | booleans, nonnumeric values, NaN, infinities, nonpositive or inconsistent values | Already fail-closed |
| Webhook connect, write, total, and HTTP read timeouts | finite `int` or `float` in `(0, 300]`; connect/write cannot exceed total | booleans, nonnumeric values, NaN, infinities, nonpositive values, oversized integers, above maximum | Confirmed non-finite/type gaps fixed |
| Webhook request, response, address, redirect, header, body, and informational-response counts | positive integers, except redirects in `[0, 5]`; addresses in `[1, 64]` | booleans, non-integers, nonpositive or out-of-range values | Already bounded; boolean request-size gap fixed |
| Webhook retention batch size | integer in `[1, 10000]` | booleans, non-integers, zero, negative and above maximum | Confirmed type gap fixed |
| Taskiq worker execution budget | `timedelta` in `(0, 1 hour]` | wrong types, nonpositive and above maximum | Wrong-type path fixed; existing domain retained |
| Taskiq worker control-plane budget | `timedelta` in `(0, 5 minutes]` | wrong types, nonpositive and above maximum | Wrong-type path fixed; existing domain retained |
| Taskiq recovery batch and enqueue age | batch integer in `[1, 10000]`; positive `timedelta` enqueue age | booleans, non-integers, invalid range and nonpositive duration | Confirmed type gaps fixed |
| Webhook rotation overlap request | integer seconds in `[1, 2592000]` | request-schema type/range validation | Reviewed; unchanged |
| Command body bounds | positive integer limits with a 16 MiB request-read ceiling | boolean/non-integer checks at fingerprint boundary and bounded streaming reads | Reviewed; no policy change in this task |

These bounds are configuration contracts, not performance promises. Retry and lease
relationships may narrow what is valid even when each individual number falls within
its basic domain. Provisional optional-integration helpers retain their security and
recovery regression obligations under ADR-017.

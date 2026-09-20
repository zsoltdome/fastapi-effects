# Command idempotency operations

## Conflict and rollback

HTTP 409 means the opaque identity is already bound to another subject or request
fingerprint, or an unexpected committed in-progress record exists. The response is
intentionally generic. Do not log the request key or compare it with durable values.

Application exceptions, cancellation, unsafe response capture, missing completion,
and effect-publication failures roll back the command claim and protected business
writes. A later identical request may execute normally. Database commit remains the
point at which a completed response becomes replayable.

## Expiry and retention

Expiry permits a new generation on the next request. It does not delete historical
completed data. Retention uses the relay credential and deletes only expired
`completed` or `superseded` rows in bounded, skip-locked batches:

```bash
fastapi-effects commands prune \
  --dsn "$FASTAPI_EFFECTS_DATABASE_DSN" \
  --before 2026-08-01T00:00:00Z \
  --batch-size 500
```

The relay role cannot select, insert, or update command rows directly. It can only
execute the reviewed pruning function. Run repeated bounded batches from a
scheduler; monitor deleted counts and transaction latency.

## External effects

The command transaction protects PostgreSQL business writes and FastAPI Effects effect
intent. It cannot atomically commit a direct HTTP call, email, broker publish, or
other remote side effect. Emit durable effect intent inside `CommandContext`, then
let the polling relay deliver it at least once with stable delivery identity.

Back up command rows with the application data they protect. After restore, preserve
the same schema revision, trigger, RLS policies, and pruning function. Treat loss of
unexpired completed rows as loss of replay protection.

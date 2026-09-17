# Deduplicating webhook receiver

Install the webhook extra, set the one-time secret returned when a subscription
is created, and run the example:

```console
export WEBHOOK_SIGNING_SECRET='whsec_...'
uvicorn examples.webhook_receiver.app:app --port 8081
```

The example verifies the exact body bytes, rejects attempts outside a five-minute
past/future window, rejects duplicate security headers, and streams the request through
a 1 MiB default limit. `WEBHOOK_MAX_AGE_SECONDS`,
`WEBHOOK_MAX_FUTURE_SKEW_SECONDS`, and `WEBHOOK_MAX_BODY_BYTES` may narrow or tune these
bounded policies. The process-local digest map demonstrates `webhook-id` deduplication
and conflicting-body rejection only; it is lost on restart and is not shared by workers.

Production receivers must replace it with a unique row keyed by a trusted endpoint/key
namespace plus `webhook-id`, inserted in the same transaction as the local business
change. Retain that row for the producer's retry/manual-redelivery horizon, not merely
the short freshness window. External effects still need their own outbox or idempotency
contract.

`examples/webhook_receiver/inbox.py` supplies an executable PostgreSQL pattern. Its
composite primary key is `(source_namespace, message_id)`; the namespace must come from
trusted endpoint/key configuration after signature verification. `apply_once()` inserts
that identity and invokes the local effect inside the caller's transaction. Concurrent
duplicates and post-restart duplicates return success-compatible duplicate results,
rollback leaves the identity reusable, and the same identity with another body digest
raises a conflict.

## Rotation and replay walkthrough

1. Configure the one-time secret returned at subscription creation as
   `WEBHOOK_SIGNING_SECRET`.
2. Rotate the subscription secret with an overlap interval. During overlap the sender
   emits signatures from both eligible versions; configure the receiver with the old
   and newly returned values as comma-separated `WEBHOOK_SIGNING_SECRETS`.
3. Confirm delivery using the new secret, remove the old value, then explicitly revoke
   the retiring version. Never revoke first and hope retries repair the gap.
4. An automatic retry retains `webhook-id` and returns `duplicate: true` after the first
   accepted request. A manual replay receives a new linked ID and is intentionally
   accepted as a new receiver operation.

If every key in an old delivery's immutable secret-set snapshot is revoked or expired,
ordinary replay stays unsignable. Create and distribute a new secret set and update the
subscription for future publications; do not reactivate revoked material or imply that
updating the subscription retargets historical work.

See the [webhook secret](../../docs/operations/webhook-secrets.md) and
[replay](../../docs/operations/retries-and-replay.md) runbooks before using this
sequence outside a local demo. The example environment variables are process
configuration, not a production secret manager.

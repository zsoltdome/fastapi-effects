# Deduplicating webhook receiver

Install the webhook extra, set the one-time secret returned when a subscription
is created, and run the example:

```console
export WEBHOOK_SIGNING_SECRET='whsec_...'
uvicorn examples.webhook_receiver.app:app --port 8081
```

The example verifies the exact body bytes and deduplicates by `webhook-id`.
Production receivers should replace the in-memory set with a unique database row
inserted in the same transaction as the receiver's business change.

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

See the [webhook secret](../../docs/operations/webhook-secrets.md) and
[replay](../../docs/operations/retries-and-replay.md) runbooks before using this
sequence outside a local demo. The example environment variables are process
configuration, not a production secret manager.

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

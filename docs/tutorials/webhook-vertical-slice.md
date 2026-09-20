# Invoice webhook vertical slice

1. Apply the core and webhook migrations with the migration-owner role.
2. Construct `WebhookSecretService` from a deployment master-key provider and
   create `SubscriptionRepository`, `WebhookOperations`, and
   `WebhookRouteProvider`.
3. Pass the route provider to `FastAPIEffects(route_providers=(...))` or directly to a
   unit of work. Create a subscription for `invoice.created`; copy its one-time
   signing secret into the receiver.
4. In the invoice endpoint, insert the invoice and call `uow.emit(...)` in the
   same `async with uow` block. The invoice, event, and versioned webhook delivery
   commit together.
5. Run `PollingRelay` with `WebhookDeliverySink`. A failed 503 schedules a retry;
   a later 2xx finalizes the same delivery identity.
6. The receiver verifies Standard Webhooks headers and uniquely records
   `webhook-id` in its business transaction. This makes an ambiguous retry have
   one effective receiver outcome.
7. A manual replay of a terminal delivery creates a linked, new message identity.

The runnable receiver is in `examples/webhook_receiver`. For local HTTP-only
testing, explicitly construct development-mode endpoint/transport policy; never
carry that override into a production relay.

# Invoicing runtime vertical slice

This example exercises the cumulative M8 runtime:

- FastAPI authenticates and binds a tenant before opening the application session;
- the outer Mergen UoW commits the invoice, event, and frozen delivery together;
- a polling relay claims the delivery without holding locks during handler work;
- the handler restores attenuated authority and opens a fresh tenant-bound application
  session; and
- the render record and terminal delivery state demonstrate end-to-end completion.

`invoice_id` is the consumer's durable business-deduplication identity. The handler
uses `INSERT ... ON CONFLICT DO NOTHING` in the same tenant-bound transaction as its
verification read. An automatic retry keeps the delivery ID and returns success when
the render already exists. A manual replay has a new delivery ID but intentionally
keeps the one-render-per-invoice business result.

The FastAPI lifespan creates one application-role pool per process. The relay factory
in `examples.invoicing.relay:create_relay` creates a distinct relay-role pool and an
application-role pool for handlers, then disposes both after bounded shutdown. The
fixed demo principal and authorization resolver illustrate protocol shape only; they
are not production authentication or authorization providers.

Boot-only tests need no database:

```bash
pytest examples/invoicing/tests -q
```

The live vertical slice is `tests/integration/test_invoicing_postgres_boot.py` and uses
`MERGEN_TEST_ADMIN_DSN` like the rest of the PostgreSQL integration suite.

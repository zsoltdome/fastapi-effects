# Invoicing runtime vertical slice

This example exercises the cumulative M8 runtime:

- FastAPI authenticates and binds a tenant before opening the application session;
- the outer Mergen UoW commits the invoice, event, and frozen delivery together;
- a polling relay claims the delivery without holding locks during handler work;
- the handler restores attenuated authority and opens a fresh tenant-bound application
  session; and
- the render record and terminal delivery state demonstrate end-to-end completion.

Boot-only tests need no database:

```bash
pytest examples/invoicing/tests -q
```

The live vertical slice is `tests/integration/test_invoicing_postgres_boot.py` and uses
`MERGEN_TEST_ADMIN_DSN` like the rest of the PostgreSQL integration suite.

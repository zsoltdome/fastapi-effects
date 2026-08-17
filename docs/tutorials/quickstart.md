# PostgreSQL quickstart

This quickstart reaches a committed application row, event, delivery, relay claim, and
fresh tenant-bound handler transaction. Clone the repository, start a disposable
PostgreSQL 16 or 18 instance, and install all test extras:

```console
uv sync --group test --all-extras
export MERGEN_TEST_ADMIN_DSN=postgresql://postgres:postgres@127.0.0.1:55432/postgres
uv run pytest -q tests/integration/test_invoicing_postgres_boot.py
```

The test creates isolated migration/application/relay roles and a database, applies the
schema, boots `examples.invoicing.app.main:app`, creates an invoice through FastAPI, and
runs the polling relay until the tenant-bound handler commits its render record. The
fixture then drops the disposable database and roles.

The application composition is in `examples/invoicing`: authentication resolves a
validated `Principal` before the async session; `Mergen.uow_dependency()` creates an
unentered outer UoW; the route enters `async with uow`, writes the invoice, and emits the
event. Any exception rolls back all three local facts. The relay uses its distinct role
only to claim/finalize Mergen tables; handler code opens a fresh application session.

For a long-running local environment, follow `examples/deployment`. Never give the app
or relay migration-owner credentials, and never expose the disposable test administrator
DSN to an application process.

# Installed-package PostgreSQL quickstart

This journey runs a persistent FastAPI process and relay from an installed wheel. It
keeps administrator, migration, application, and relay credentials separate. Commands
assume a checkout only for the example application; `fastapi_mergen` itself is imported
from the wheel, not `src/`.

## 1. Build and install the package

```console
uv build
python -m venv .quickstart
.quickstart/bin/python -m pip install dist/*.whl uvicorn
cp examples/deployment/.env.example examples/deployment/.env
```

Replace every password in `.env`; these local demo values are not production secret
management. Start PostgreSQL:

```console
docker compose --env-file examples/deployment/.env \
  -f examples/deployment/compose.yml up -d postgres
set -a
. examples/deployment/.env
set +a
```

## 2. Bootstrap roles and migrate

The administrator is used once to create login roles. Runtime processes never receive
that credential.

```console
docker compose --env-file examples/deployment/.env \
  -f examples/deployment/compose.yml exec -T postgres \
  psql -U postgres -d mergen \
  -v migration_password="$MERGEN_MIGRATION_PASSWORD" \
  -v application_password="$MERGEN_APPLICATION_PASSWORD" \
  -v relay_password="$MERGEN_RELAY_PASSWORD" \
  < examples/deployment/bootstrap.sql

MERGEN_DATABASE_DSN="$MERGEN_EXAMPLE_MIGRATION_DATABASE_URL" \
  .quickstart/bin/fastapi-mergen schema upgrade --no-create-runtime-roles
PYTHONPATH=. .quickstart/bin/python -m examples.invoicing.bootstrap
```

Check both least-privileged roles without printing either DSN:

```console
MERGEN_DATABASE_DSN="$MERGEN_EXAMPLE_DATABASE_URL" \
  .quickstart/bin/fastapi-mergen doctor --expected-role mergen_app
MERGEN_DATABASE_DSN="$MERGEN_EXAMPLE_RELAY_DATABASE_URL" \
  .quickstart/bin/fastapi-mergen doctor --expected-role mergen_relay
```

## 3. Start the application and relay

Use separate terminals with the exported `.env` values:

```console
PYTHONPATH=. .quickstart/bin/uvicorn examples.invoicing.app.main:app \
  --host 127.0.0.1 --port 8000
```

```console
PYTHONPATH=. .quickstart/bin/fastapi-mergen relay run \
  --factory examples.invoicing.relay:create_relay
```

Create an invoice:

```console
curl --fail-with-body -X POST http://127.0.0.1:8000/invoices \
  -H 'authorization: Bearer milestone-one-demo' \
  -H 'x-tenant-id: 11111111-1111-4111-8111-111111111111' \
  -H 'content-type: application/json' \
  -d '{"customer_id":"22222222-2222-4222-8222-222222222222", "amount":"10.50", "currency":"EUR"}'
```

The response identifies the invoice. The application transaction committed the
invoice, event, and delivery together; the relay then records a render and finalizes
the delivery. Stop the relay with `SIGTERM` or Ctrl-C: admission stops immediately,
active work drains only through its configured grace, and unfinished leases remain
recoverable.

## 4. Verify rollback, retry, and replay identities

The executable integration journey exercises facts that are awkward to trigger by
hand: an application exception rolls back business/event/delivery rows; a consumer
commit followed by lost relay finalization retries with the same delivery ID and a new
attempt ID; the conflict-safe render remains one row. Run it against a disposable test
database when developing:

```console
MERGEN_TEST_ADMIN_DSN=postgresql://postgres:postgres@127.0.0.1:55432/postgres \
  uv run pytest -q tests/integration/test_invoicing_postgres_boot.py \
  tests/integration/test_core_concurrency.py::test_fanout_failure_rolls_back_business_and_event_rows
```

Automatic retry preserves the delivery/message ID. Manual replay creates a new
delivery/message ID linked through `replay_of`; the invoice example deliberately uses
`invoice_id` as its business dedupe key, so replay still produces one render.

## Next: signed webhooks

Continue with the [webhook vertical slice](webhook-vertical-slice.md) and the runnable
signature-verifying receiver in `examples/webhook_receiver`. The core quickstart does
not require Redis, Taskiq, or FastMCP.

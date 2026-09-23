# Installed-package PostgreSQL quickstart

This journey installs an exact public release, checks out examples from the matching
tag, and runs a persistent FastAPI process and relay. It keeps administrator,
migration, application, and relay credentials separate. The example checkout is never
installed as the library: `fastapi_effects` must resolve inside `.quickstart`.

## 1. Install the exact published package and matching examples

```console
export FASTAPI_EFFECTS_VERSION=0.11.0a2
git clone --depth 1 --branch "v${FASTAPI_EFFECTS_VERSION}" \
  https://github.com/zsoltdome/fastapi-effects.git \
  "fastapi-effects-${FASTAPI_EFFECTS_VERSION}"
cd "fastapi-effects-${FASTAPI_EFFECTS_VERSION}"
python -m venv .quickstart
.quickstart/bin/python -m pip install --no-cache-dir \
  "fastapi-effects[webhooks]==${FASTAPI_EFFECTS_VERSION}" uvicorn
.quickstart/bin/python -c \
  'from importlib.metadata import version; print(version("fastapi-effects"))'
git describe --tags --exact-match
cp examples/deployment/.env.example examples/deployment/.env
```

Both commands must print the selected version/tag. For a not-yet-published candidate,
use only the exact retained candidate wheel and matching source archive supplied by the
release workflow; never combine a candidate artifact with moving `main` examples.

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
  psql -U postgres -d fastapi_effects \
  -v migration_password="$FASTAPI_EFFECTS_MIGRATION_PASSWORD" \
  -v application_password="$FASTAPI_EFFECTS_APPLICATION_PASSWORD" \
  -v relay_password="$FASTAPI_EFFECTS_RELAY_PASSWORD" \
  < examples/deployment/bootstrap.sql

FASTAPI_EFFECTS_DATABASE_DSN="$FASTAPI_EFFECTS_EXAMPLE_MIGRATION_DATABASE_URL" \
  .quickstart/bin/fastapi-effects schema upgrade --no-create-runtime-roles
PYTHONPATH=. .quickstart/bin/python -m examples.invoicing.bootstrap
```

Check both least-privileged roles without printing either DSN:

```console
FASTAPI_EFFECTS_DATABASE_DSN="$FASTAPI_EFFECTS_EXAMPLE_DATABASE_URL" \
  .quickstart/bin/fastapi-effects doctor --expected-role fastapi_effects_app
FASTAPI_EFFECTS_DATABASE_DSN="$FASTAPI_EFFECTS_EXAMPLE_RELAY_DATABASE_URL" \
  .quickstart/bin/fastapi-effects doctor --expected-role fastapi_effects_relay
```

## 3. Start the application and relay

Use separate terminals with the exported `.env` values:

```console
PYTHONPATH=. .quickstart/bin/uvicorn examples.invoicing.app.main:app \
  --host 127.0.0.1 --port 8000
```

```console
PYTHONPATH=. .quickstart/bin/fastapi-effects relay run \
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
attempt ID; the conflict-safe render remains one row. Install the test runner into the
same consumer environment and run the journey against a disposable test database:

```console
.quickstart/bin/python -m pip install "pytest>=9,<10" "pytest-asyncio>=1.3,<2"
FASTAPI_EFFECTS_TEST_ADMIN_DSN=postgresql://postgres:postgres@127.0.0.1:55432/postgres \
  .quickstart/bin/python -m pytest -q tests/integration/test_invoicing_postgres_boot.py \
  tests/integration/test_core_concurrency.py::test_fanout_failure_rolls_back_business_and_event_rows
```

Automatic retry preserves the delivery/message ID. Manual replay creates a new
delivery/message ID linked through `replay_of`; the invoice example deliberately uses
`invoice_id` as its business dedupe key, so replay still produces one render.

## Next: signed webhooks

Continue with the [webhook vertical slice](webhook-vertical-slice.md) and the runnable
signature-verifying receiver in `examples/webhook_receiver`. The core quickstart does
not require Redis, Taskiq, or FastMCP.

## Contributor build appendix

Contributors validating an unpublished source change can build it locally. This is not
the consumer installation path and its output has no release authority until the
protected artifact workflow certifies the exact bytes.

```console
uv sync --locked --all-extras --all-groups
uv build --no-sources
uv run --locked --no-sync python scripts/check.py
```

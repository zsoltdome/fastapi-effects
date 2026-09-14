# Persistent local deployment reference

This reference keeps four authorities separate: the local PostgreSQL administrator,
`mergen_migration`, `mergen_app`, and `mergen_relay`. It is a topology teaching aid,
not a high-availability design.

```console
cp examples/deployment/.env.example examples/deployment/.env
# replace every password
docker compose --env-file examples/deployment/.env \
  -f examples/deployment/compose.yml up -d postgres
set -a; . examples/deployment/.env; set +a
```

Create the login roles with the administrator, run the package's bundled migrations
with only the migration credential, then create the example-owned business tables:

```console
docker compose --env-file examples/deployment/.env \
  -f examples/deployment/compose.yml exec -T postgres \
  psql -U postgres -d mergen \
  -v migration_password="$MERGEN_MIGRATION_PASSWORD" \
  -v application_password="$MERGEN_APPLICATION_PASSWORD" \
  -v relay_password="$MERGEN_RELAY_PASSWORD" \
  < examples/deployment/bootstrap.sql
MERGEN_DATABASE_DSN="$MERGEN_EXAMPLE_MIGRATION_DATABASE_URL" \
  fastapi-mergen schema upgrade --no-create-runtime-roles
python -m examples.invoicing.bootstrap
```

Run the FastAPI process with `MERGEN_EXAMPLE_DATABASE_URL` and the relay with both
`MERGEN_EXAMPLE_RELAY_DATABASE_URL` (control plane) and
`MERGEN_EXAMPLE_DATABASE_URL` (tenant-bound handlers). The relay factory is
`examples.invoicing.relay:create_relay`.

Pin the PostgreSQL image by digest in production, use TLS off-host, source credentials
from a secret manager, set pool/resource limits, and test backup/PITR before traffic.

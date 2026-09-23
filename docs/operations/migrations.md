# Schema migrations

Package and database versions are separate. The candidate migration head is
`0005_webhook_retention`; the frozen component registry is:

| Alembic revision | Component revision | Objects introduced |
| --- | --- | --- |
| `0001_core_runtime` | `core=1` | events, deliveries, attempts, forced RLS and roles |
| `0002_webhooks` | `webhooks=1` | subscriptions, encrypted secret metadata, audit |
| `0003_taskiq` | `executor.taskiq=1` | durable handoffs |
| `0004_commands` | `commands=1` | command generations, guards, bounded pruning |
| `0005_webhook_retention` | `webhooks=2` | tenant-bound bounded webhook retention |

Run Alembic only with the migration-owner credential. Application and relay credentials
must never own tables, functions, indexes, policies, or triggers. Deploy schema changes
before starting candidate application processes, then run:

The installed CLI exposes the bundled revision set through `fastapi-effects schema
upgrade --dsn ...`. When an administrator has already created the three login roles,
pass `--no-create-runtime-roles`; the migration process then needs no role-creation
authority. The explicit Alembic environment remains available for advanced deployment
or downgrade procedures.

```console
fastapi-effects schema check --dsn postgresql://...
fastapi-effects doctor --dsn postgresql://... --expected-role fastapi_effects_app
```

Applications should also await `PostgresStore().check_schema(engine)` in their startup
lifecycle. The check is read-only, requires exact revisions, rejects missing/older/newer
components, and never invokes Alembic.

Every published revision is upgraded to head in the PostgreSQL 16/18 matrix with seeded
rows. Tests verify row preservation, ownership, forced RLS, and the command mutation
trigger. Revisions `0001` through `0005` use immutable versioned DDL and security SQL,
not current ORM collections or current grant/RLS helpers. A golden digest detects any
attempt to rewrite that published migration contract; schema evolution requires a new
revision. Empty-schema downgrades are supported for disposable environments. A
downgrade that would drop a nonempty component is deliberately rejected.
Revision `0005_webhook_retention` has a data-preserving downgrade to `0004_commands`:
it removes only the retention function and restores the webhook marker to revision 1.

The 2026-09-07 [published-artifact inventory](../audits/2026-09-07/published-artifact-inventory.json)
is preserved as point-in-time evidence from before a public release existed. The
[current release inventory](../audits/2026-09-23/release-inventory.json) records the
schema-bearing `0.11.0a1` wheel published on September 20. Historical-artifact upgrade
testing is therefore required for every later candidate: install the exact public
wheel, create and seed its schema, then upgrade with the exact candidate wheel on
PostgreSQL 16 and 18 while checking data, ownership, roles, grants, forced RLS,
constraints, indexes, and component revision markers.

For a production rollback, stop writers and relays, retain the old application artifact,
take and verify a logical backup, restore it into a separate database, run the desired
downgrade there, run doctor and conformance, and only then redirect traffic. Never delete
component rows merely to pass the downgrade guard. Forward-fixing the application is the
preferred recovery after a schema has accepted production data.

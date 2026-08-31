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

```console
fastapi-mergen schema check --dsn postgresql://...
fastapi-mergen doctor --dsn postgresql://... --expected-role mergen_app
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
found no PyPI/TestPyPI release, local repository tag, or retained historical
distribution. Upgrading from a historical published artifact is therefore recorded as
`NOT_APPLICABLE`, with the explicit limitation that any privately retained artifact
outside this workspace must be added to the inventory before candidate approval.

For a production rollback, stop writers and relays, retain the old application artifact,
take and verify a logical backup, restore it into a separate database, run the desired
downgrade there, run doctor and conformance, and only then redirect traffic. Never delete
component rows merely to pass the downgrade guard. Forward-fixing the application is the
preferred recovery after a schema has accepted production data.

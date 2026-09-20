# Backup and restore

Use PostgreSQL physical/PITR tooling for the database service's recovery objectives and a
logical custom-format backup before every migration, retention-policy change, key
operation, or bulk replay. Include the entire `fastapi_effects` schema and role/grant
definitions. Store backups encrypted with separately managed access; a backup contains
event payloads, principals, response bodies, and encrypted webhook secret material.

Example logical rehearsal (use `.pgpass`, a secret manager, or short-lived credentials;
do not put production passwords in shell history):

```console
pg_dump --format=custom --no-owner --schema=fastapi_effects --file=fastapi_effects.dump "$SOURCE_DSN"
createdb fastapi_effects_restore_rehearsal
alembic upgrade head
pg_restore --data-only --no-owner --dbname="$RESTORED_DSN" fastapi_effects.dump
python scripts/verify_restore.py --source-dsn "$SOURCE_DSN" --restored-dsn "$RESTORED_DSN"
fastapi-effects schema check --dsn "$RESTORED_APP_DSN"
fastapi-effects doctor --dsn "$RESTORED_APP_DSN" --expected-role fastapi_effects_app
```

The verifier compares every row of schema revisions, events, deliveries, attempts,
subscriptions, encrypted secret records and audit, Taskiq handoffs, and commands. It
hashes values locally and reports only table names, counts, and digests. The source and
restore must be separate databases.

After verification, run the real core, delivery, security, webhook, executor, command,
and delegation conformance profiles in the restored environment. Confirm that migration
ownership, grants, forced RLS, functions, indexes, and triggers match the registry before
opening traffic. Destroy the rehearsal database and backup according to policy.

The repository exercises this complete logical restore sequence on PostgreSQL 16 and
18. The automated rehearsal compares protected row identities, runs schema checks,
doctor and backlog probes, clears only the restored test workload, and then executes all
applicable real conformance profiles against the restored deployment.

For a compromised webhook or delegation key, preserve the backup for investigation but
revoke/rotate in the live control plane; restoring an old database must not reactivate a
revoked external key. For a failed migration, stop writers, preserve both databases, and
follow the separate-restore procedure in the migrations guide.

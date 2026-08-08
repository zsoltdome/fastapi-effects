# ADR-014: Tenant-bound webhook retention

**Status:** accepted
**Date:** 2026-08-30

## Decision

Webhook history pruning is a dedicated maintenance transaction executed through a
`SECURITY DEFINER` PostgreSQL function owned by the migration role. The function has a
fixed `search_path`, accepts an explicit tenant, cutoff, and bounded batch size, and
rejects a tenant that does not equal the transaction-local `mergen.tenant_id` setting.
Only the application role receives `EXECUTE`; it receives no new direct delete grant on
immutable core history.

One call prunes, in dependency order, finished attempts belonging to terminal webhook
deliveries, terminal deliveries without attempts, orphan events, and old retiring or
revoked webhook secret versions. Pending, leased, and retry-wait deliveries are never
eligible. Each stage independently caps work at the requested batch size and uses
`FOR UPDATE SKIP LOCKED`, so calls are bounded, concurrent, and resumable.

`WebhookOperations.retain()` requires an idle session, owns and commits the maintenance
transaction, binds tenant and subject context, and emits aggregate telemetry only after
commit. Telemetry failure remains isolated from the committed database outcome.

## Consequences

- Webhook component revision 2 and Alembic revision `0005_webhook_retention` are required.
- Downgrading this revision removes only the maintenance function and restores the
  webhook component marker to revision 1; it does not remove data.
- Operators repeat small committed batches until every returned count is zero.
- Retention cannot be mixed into an application business transaction or used across
  tenants with one call.

## Rejected alternatives

- Granting direct core-table deletion to the application or relay roles broadens their
  authority over immutable history.
- ORM deletion inside a caller-owned transaction cannot truthfully emit post-commit
  observations and did not have sufficient core-table grants.
- Unbounded cascading deletion creates lock and latency risks and is not resumable.

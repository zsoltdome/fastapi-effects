# PostgreSQL roles and row-level security

## Fixed role model

| Role | Runtime | Owns objects | Tenant visibility | Required privileges |
|---|---:|---:|---|---|
| `fastapi_effects_migration` | No | Yes | Administrative | Schema/table/policy DDL |
| `fastapi_effects_app` | Yes | No | One transaction-bound tenant | Application and tenant-scoped FastAPI Effects operations |
| `fastapi_effects_relay` | Yes | No | All tenants on FastAPI Effects control tables only | Claim/read/finalize deliveries and attempts; no application tables; no delete history |

Runtime roles must not be superusers, object owners, or members of a role with
`BYPASSRLS`. The migration credential must not be deployed to application or relay
processes.

## Transaction-local tenant context

The UoW executes these settings before application SQL:

```sql
SELECT pg_catalog.set_config(
    'fastapi_effects.tenant_id',
    :tenant_id,
    true
);
SELECT pg_catalog.set_config('fastapi_effects.subject_id', :subject_id, true);
```

`true` makes each setting local to the current transaction. Policies use
`NULLIF(current_setting('fastapi_effects.tenant_id', true), '')::uuid`; missing context returns
`NULL` and denies all tenant rows, while malformed context fails closed.

## Policy shape

Every FastAPI Effects tenant table has RLS enabled and forced:

```sql
ALTER TABLE fastapi_effects.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE fastapi_effects.events FORCE ROW LEVEL SECURITY;
```

The request/handler role requires both read visibility and write validation:

```sql
CREATE POLICY events_application_tenant
ON fastapi_effects.events
FOR ALL
TO fastapi_effects_app
USING (tenant_id = NULLIF(current_setting('fastapi_effects.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('fastapi_effects.tenant_id', true), '')::uuid);
```

The relay receives separate, explicit policies only on FastAPI Effects-owned tables. It does
not receive a general application-schema grant.

## Ownership and search path

- Objects are owned by `fastapi_effects_migration` (or the explicitly configured migration role).
- SQL and migrations are schema-qualified.
- Security-definer functions, if admitted later, use a fixed safe `search_path` and
  have narrowly granted execution.
- Runtime roles must not be able to create writable objects in any schema that
  precedes trusted schemas on the search path.
- The public schema must not be an implicit extension point for privileged SQL.

## `fastapi-effects doctor` probes

Diagnostics run as the engine's actual configured role and verify:

1. superuser, ownership, membership, and `BYPASSRLS` status;
2. expected schema/table/function owners;
3. RLS enabled and forced on every tenant table;
4. expected app and relay policies;
5. live `USING` and `WITH CHECK` denial probes;
6. missing-context default denial;
7. setting reset after commit and rollback;
8. pool reuse without a prior tenant;
9. relay denial on configured application tables;
10. package/schema revision compatibility.

Critical failure produces a non-zero exit. Output is bounded and never includes the
configured DSN, passwords, payloads, or secrets.

## Security limitation

The app credential is a trusted service credential. Its holder can issue
`set_config()` for another tenant. RLS therefore protects against missing filters and
classes of application mistakes; it does not protect against complete compromise of
the application process or its database credential.

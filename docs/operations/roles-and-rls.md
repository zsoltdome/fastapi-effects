# PostgreSQL roles and row-level security

## Fixed role model

| Role | Runtime | Owns objects | Tenant visibility | Required privileges |
|---|---:|---:|---|---|
| `mergen_migration_owner` | No | Yes | Administrative | Schema/table/function/policy DDL |
| `mergen_app` | Yes | No | One transaction-bound tenant | Application and tenant-scoped Mergen operations |
| `mergen_relay` | Yes | No | All tenants on Mergen control tables only | Claim/read/finalize deliveries and attempts; no application tables; no delete history |

Runtime roles must not be superusers, object owners, or members of a role with
`BYPASSRLS`. The migration credential must not be deployed to application or relay
processes.

## Transaction-local tenant context

The planned UoW executes this before application SQL:

```sql
SELECT pg_catalog.set_config(
    'fastapi_mergen.tenant_id',
    :tenant_id,
    true
);
```

`true` makes the setting local to the current transaction. The fail-closed helper is
schema-qualified and returns `NULL` when no value exists:

```sql
CREATE FUNCTION fastapi_mergen.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT NULLIF(
        pg_catalog.current_setting('fastapi_mergen.tenant_id', true),
        ''
    )::uuid
$$;
```

A malformed value raises rather than selecting an arbitrary tenant.

## Policy shape

Every Mergen tenant table has RLS enabled and forced:

```sql
ALTER TABLE fastapi_mergen.event ENABLE ROW LEVEL SECURITY;
ALTER TABLE fastapi_mergen.event FORCE ROW LEVEL SECURITY;
```

The request/handler role requires both read visibility and write validation:

```sql
CREATE POLICY event_app_policy
ON fastapi_mergen.event
FOR ALL
TO mergen_app
USING (tenant_id = fastapi_mergen.current_tenant_id())
WITH CHECK (tenant_id = fastapi_mergen.current_tenant_id());
```

The relay receives separate, explicit policies only on Mergen-owned tables. It does
not receive a general application-schema grant.

## Ownership and search path

- Objects are owned by `mergen_migration_owner`.
- SQL and migrations are schema-qualified.
- Security-definer functions, if admitted later, use a fixed safe `search_path` and
  have narrowly granted execution.
- Runtime roles must not be able to create writable objects in any schema that
  precedes trusted schemas on the search path.
- The public schema must not be an implicit extension point for privileged SQL.

## `fastapi-mergen doctor` planned probes

Milestone 2 diagnostics must run as actual configured roles and verify:

1. superuser, ownership, membership, and `BYPASSRLS` status;
2. expected schema/table/function owners;
3. RLS enabled and forced on every tenant table;
4. expected app and relay policies;
5. live `USING` and `WITH CHECK` denial probes;
6. missing-context default denial;
7. setting reset after commit and rollback;
8. pool reuse without a prior tenant;
9. relay denial on configured application tables;
10. unsafe writable search-path objects;
11. package/schema revision compatibility.

Critical failure produces a non-zero exit. Human and JSON output must redact passwords,
credential-bearing DSNs, payloads, and secrets.

## Security limitation

The app credential is a trusted service credential. Its holder can issue
`set_config()` for another tenant. RLS therefore protects against missing filters and
classes of application mistakes; it does not protect against complete compromise of
the application process or its database credential.

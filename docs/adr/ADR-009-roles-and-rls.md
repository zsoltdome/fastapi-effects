# ADR-009: PostgreSQL roles and row security

- Status: Accepted
- Date: 2026-08-30

The migration owner owns schema objects and is not a runtime credential. `mergen_app`
may operate only tenant rows selected by transaction-local `mergen.tenant_id` and
`mergen.subject_id`. `mergen_relay` receives narrowly enumerated control-plane grants
and is never injected into application handlers.

Runtime roles must not be superusers, table owners, or `BYPASSRLS`. Tenant tables enable
and force RLS. Application policies specify both `USING` and `WITH CHECK`; absent or
invalid tenant context denies by default. Security-definer helpers fix `search_path` and
revoke public execution. `doctor` verifies live role behavior rather than trusting DDL.

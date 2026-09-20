# ADR 0001: Fix the trust and role model

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

Tenant isolation can fail when runtime roles own tables, bypass RLS, inherit unsafe
grants, or reuse a cross-tenant relay connection inside application handlers. The
application-set tenant GUC is context propagation and must not be presented as
end-user database authentication.

## Decision

Use exactly three required roles:

1. `fastapi_effects_migration` owns schema objects and never runs in application/relay
   processes;
2. `fastapi_effects_app` owns nothing, has no bypass privileges, and is constrained by forced
   RLS to the transaction-bound tenant;
3. `fastapi_effects_relay` owns nothing and receives cross-tenant operations only on FastAPI Effects
   control-plane tables, with no application-table or history-delete grant.

Internal handlers obtain a fresh `fastapi_effects_app` session. Relay sessions are not part of
`EffectContext` and cannot be injected through supported handler providers.

## Consequences

- Managed platforms may disable role creation, but must apply equivalent documented
  grants and pass live diagnostics.
- Migration, app, and relay DSNs are separate configuration values.
- A compromised app credential can deliberately bind another tenant; this residual
  risk is explicit.
- `doctor` must inspect ownership, role flags, policies, grants, search path, and live
  denial behavior.

## Rejected alternatives

- one owner role for migration and runtime — table-owner RLS bypass risk;
- one cross-tenant runtime role — unnecessary application-data exposure;
- relying on application query filters — does not contain omitted-filter bugs;
- presenting a tenant header/GUC as authentication — incorrect trust claim.

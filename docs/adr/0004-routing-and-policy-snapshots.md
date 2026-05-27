# ADR 0004: Freeze routes and snapshot policy

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

Retrying work through a changed route, subscription, retry profile, or authorization
configuration can silently alter committed intent or expand authority.

## Decision

- Register exact event-type routes before startup completes.
- Give each route an explicit stable key and positive version.
- Validate handlers, retry profiles, authorization resolvers, and service policies,
  then freeze the registry.
- Resolve deterministic routes during `emit()`.
- Store route key/version, destination snapshot, policy snapshot, retry values, and
  snapshot schema version per delivery.
- Store no Python callable, raw credential, or plaintext secret.

Authorization modes are limited to:

```text
snapshot:   effective = origin ∩ route allowance
revalidate: effective = current ∩ origin ceiling ∩ route allowance
service:    separately named service capability; user origin retained for causality
```

## Consequences

- Later route/subscription edits affect future emissions only.
- Unsupported snapshot versions dead-letter explicitly rather than being guessed.
- Policy snapshots are larger but replay and incident analysis remain deterministic.

## Rejected alternatives

- wildcard/filter DSL in MDP — widens correctness and security surface;
- resolve by Python function name — unstable across refactors/deploys;
- store only profile names — mutable retry/authority behavior;
- forward raw caller credentials — leakage, expiry, and audience mismatch.

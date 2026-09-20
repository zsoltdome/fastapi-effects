# Authorization and principal provenance

## Trust entry

FastAPI Effects is authentication-agnostic. A host-provided `PrincipalProvider` must:

1. authenticate the caller;
2. collect candidate tenant identifiers;
3. reject conflicting sources;
4. verify tenant membership/authority;
5. return one validated immutable `Principal`.

A raw header, subdomain, JWT claim, or API key field may suggest a tenant but is never
by itself authorization proof.

## Durable principal fields

The planned event principal snapshot includes:

- tenant ID and subject ID;
- optional actor and client IDs;
- origin scopes;
- issuance, authentication, and optional expiry times;
- an optional opaque credential/session reference;
- bounded, approved non-secret metadata.

Raw bearer tokens, cookies, API keys, session tokens, and refresh tokens are not
principal fields.

## Route-specific authorization

Authorization is snapshotted per delivery because one event may route to destinations
with different policy requirements.

### Snapshot

Use attenuated scopes captured at emission. A maximum snapshot age is mandatory.

```text
effective_scopes = origin_scopes ∩ route_allowed_scopes
```

Snapshot mode fails terminally after its maximum age unless the route explicitly
permits a separately defined revalidation fallback.

### Revalidate

Resolve current authority before each attempt while preserving the origin ceiling.

```text
effective_scopes = current_scopes
                 ∩ origin_scope_ceiling
                 ∩ route_allowed_scopes
```

Revocation is observed. A temporary authorization-provider outage is retryable within
policy limits; denied scope is terminal by default.

### Service policy

A named application-defined capability, resolved at startup, performs the action.
This is service authority—not enlarged user authority. The execution context records:

- service policy name and resolved capability set;
- originating tenant, subject, actor, and client for causality;
- a clear authority-kind marker.

An unresolved service policy fails startup.

## Non-expansion rules

- User-derived execution scopes are subsets of the origin ceiling.
- Revalidation can reduce but never expand that ceiling.
- Route allowance can reduce but never expand scopes.
- A service policy transition is explicit in route declaration and snapshots.
- No delayed execution requires loading a raw user credential from event/delivery
  storage.

## Failure mapping

| Condition | Default result |
|---|---|
| Snapshot expired | Terminal `AuthorizationExpired` |
| Revalidation denies required scope | Terminal `AuthorizationDenied` |
| Authorization provider temporarily unavailable | Retryable delivery failure |
| Service policy unresolved at startup | `FastAPIEffectsConfigurationError` |
| Stored policy schema unsupported | Terminal `SchemaRevisionMismatch` |

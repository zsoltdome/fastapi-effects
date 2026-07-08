# Mergen Boundary Contract v1.0

**Status:** accepted and executable through the Milestone 7 assurance suite.
**Contract version:** `1.0`
**Applies to:** the Mergen-owned transition from an authenticated, tenant-scoped
application operation to durable and deferred effects.

The key words **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**, and **DOES NOT** are
normative.

## 1. Boundary

```text
authenticated operation
        │ trusted Principal
        ▼
transactional command or MergenUnitOfWork
        │ tenant context bound before application SQL
        ├── application state
        ├── immutable event / command identity
        └── original delivery intents
                 │ commit
                 ▼
       handlers / executors / webhooks / delegated calls
```

Mergen owns neither caller authentication nor remote consumer behavior. The host
application supplies a trusted principal and an adapter that exposes observable
boundary operations to the conformance suite.

## 2. Three primitives

### Principal

An immutable trusted security context containing at least tenant, subject, optional
actor/client, origin scopes, authentication timestamps, and non-secret references.
A `ContextVar` may provide process-local convenience; it is not the durable security
boundary.

### Effect

An immutable typed intent persisted in the same local transaction as the application
change. Arbitrary ORM-object serialization and raw credential persistence are
forbidden.

### Delivery

One independently retryable route from one effect to one destination. Every handler,
queue handoff, webhook subscription, or delegated call owns distinct state, attempts,
retry identity, and terminal outcome.

## 3. Normative invariants

### BC-01 — Atomic intent

The implementation **MUST** commit the application mutation, event, and every original
delivery intent in one local transaction, or commit none. It **MUST NOT** invoke a
sink during effect emission.

Executable checks: `atomicity.commit`, `atomicity.rollback`.

### BC-02 — Tenant continuity

Event, delivery, attempt, execution principal, and tenant-bound application session
**MUST** identify the same tenant. Missing or conflicting tenant context **MUST** fail
closed, and a principal for one tenant **MUST NOT** inspect another tenant's boundary
state.

Executable check: `isolation.cross_tenant`.

### BC-03 — Explicit authority provenance

Every effect route **MUST** use explicit snapshot, revalidation, or named service
policy semantics. User-derived authority **MUST NOT** exceed both the historical
origin ceiling and the route allowance. Service authority **MUST NOT** masquerade as
user authority.

Executable checks: `authority.snapshot_attenuation`,
`authority.revalidation_ceiling`.

### BC-04 — Stable retry identity

Automatic retry **MUST** retain the same delivery and consumer-visible message
identity and allocate a distinct attempt identity. The implementation **DOES NOT**
promise that an external effect occurs only once.

Executable check: `delivery.retry_identity`.

### BC-05 — Independent fan-out

Each destination **MUST** own independent state, lease, attempts, retry schedule, and
terminal result. Failure or replay of one destination **MUST NOT** mutate a sibling.

Executable check: `delivery.independent_fanout`.

### BC-06 — Causal lineage

Event, delivery, attempt, tenant, subject, optional actor/client, correlation,
causation, route version, and valid trace context **MUST** remain linkable. Raw
credentials **MUST NOT** be used to preserve lineage.

Executable check: `lineage.correlation_causation`.

### BC-07 — Replay accountability

Manual replay **MUST** create a new delivery identity linked to an immutable original
terminal delivery. The original outcome **MUST NOT** return to pending.

Executable check: `replay.accountable_identity`.

### BC-08 — Lease fencing

Every claim and execution lease **MUST** have an unguessable token. Finalization,
renewal, or recovery **MUST** compare the exact active token. A stale worker **MUST
NOT** acknowledge or overwrite work reclaimed by another worker.

Executable check: `lease.stale_finalization`.

### BC-09 — Context cleanup

Principal, dependency, application-session, and executor context **MUST** be reset in
a `finally` path after success, failure, timeout, and cancellation. Sequential work
for different tenants in one process **MUST NOT** inherit prior authority.

Executable check: `lifecycle.context_cleanup`.

### BC-10 — Secret minimization

Raw bearer tokens, cookies, session values, signing keys, private keys, and reusable
credentials **MUST NOT** appear in public evidence, reports, default logs, metrics, or
exceptions. Reference identifiers such as `key_id` and `credential_ref` may be
included when they are non-secret.

Executable check: `security.secret_minimization`, plus optional deployment-provided
secret canaries.

### BC-11 — Transactional command identity

Inbound command idempotency **MUST** bind tenant, stable route, method, opaque key
digest, request fingerprint, and originating subject. Concurrent duplicates **MUST**
converge to one committed transaction and replay, while a different fingerprint or
subject **MUST** conflict.

Executable checks: `idempotency.concurrent_duplicate`,
`idempotency.fingerprint_conflict`.

### BC-12 — Delegation target binding

A delegated credential **MUST** be short lived, scope attenuated, audience bound, and
bound to the exact canonical method and path. Target mismatch **MUST** fail closed.
The original browser, MCP, or API bearer credential **MUST NOT** be forwarded as the
next-hop credential.

Executable checks: `delegation.exact_target`, `delegation.rejection_matrix`.

## 4. Guarantee vocabulary

| Boundary | Contract guarantee |
|---|---|
| Application state + event + original deliveries | Atomic local commit |
| Rolled-back operation | No committed event or original delivery |
| Delivery execution | At least once |
| Consumer-visible effect | Effectively once only with consumer deduplication |
| Automatic retry | Same delivery/message ID, new attempt ID |
| Manual replay | New linked delivery ID |
| Fan-out | Independent state per destination |
| Ordering | Not guaranteed |
| Tool visibility | Discovery control, not authorization |

Public wording:

> **Atomic publication, at-least-once delivery, and stable identities for
> effectively-once consumers.**

Delivery is at least once. Ordering and cancellation are undefined and unsupported.

## 5. Conformance profiles

- **core** — BC-01 through BC-07;
- **delivery** — retry identity, fan-out, replay, and lease fencing;
- **security** — tenant continuity, authority, lease fencing, context cleanup,
  secret minimization, and delegation binding;
- **complete** — every v1 invariant.

A profile is certified only when every required invariant has at least one passing
check and there are no failed, skipped, or errored checks. A capability declaration
cannot substitute for executable evidence.

## 6. Capability manifest

A driver publishes a strict manifest containing:

```text
schema_version
contract_version
adapter_name
adapter_version
implementation
capabilities
invariants
metadata
```

The manifest is canonicalized and identified by SHA-256. Reports bind to that exact
digest. Unknown fields, duplicate JSON keys, duplicate capability values, sensitive
metadata keys, unsupported contract versions, and missing capability prerequisites
fail validation.

## 7. Evidence rules

- Reports are deterministic apart from run identity, timestamps, duration, and
  declared environment facts.
- JSON is the authoritative archival representation.
- JUnit is provided for test systems, SARIF for code-scanning interfaces, and
  Markdown for human review.
- Evidence is bounded and normalized before serialization.
- Exception messages are not copied into public reports because they may contain
  tenant data or credentials; only bounded exception type names are retained.
- Output files are atomically replaced, private by default, and may not target a
  symbolic link.
- Archived evidence is independently verified against the exact capability manifest.

## 8. Trust boundary of the adapter

A `module:factory` adapter is imported and executed as trusted deployment code. The
CLI **MUST NOT** load an adapter specification supplied by a tenant or other untrusted
caller. The conformance suite can detect observable violations but cannot prove that
an adapter truthfully connects each protocol method to the claimed production path.
Certification therefore applies to the tested adapter, configuration, and
implementation version—not to an unrelated deployment.

## 9. Change control

Changing an invariant, guarantee, profile, manifest field, report field, or
certification rule requires:

1. a superseding ADR;
2. a contract-version and compatibility decision;
3. updated descriptor and evidence schemas;
4. new positive and injected-fault tests;
5. release notes describing certification impact.

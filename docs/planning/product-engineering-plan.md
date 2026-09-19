# FastAPI-Mergen — Product and Engineering Plan

**Date:** 2026-08-24  
**Current baseline:** 2026-09-07, production-hardening alpha `0.11.0a1`
**Status:** substantial runtime exists; repaired behavior needs candidate-bound hosted
and external verification before a production-support promise
**Distribution:** `fastapi-mergen`  
**Import package:** `fastapi_mergen`  
**Console command:** `fastapi-mergen`  
**Market category:** tenant-safe effects  
**Technical category:** principal-preserving transactional eventing

The scorecard and milestone estimates below are preserved as the historical design
baseline. They are not the current implementation status. The repository now contains
the PostgreSQL runtime, handlers, webhooks, Taskiq handoffs, command idempotency,
delegation/FastMCP, migrations, operations, and conformance adapters. The truthful
recovery provenance remains in [runtime-recovery.md](runtime-recovery.md); current
capability maturity and evidence are tracked separately in
[capability-evidence-ledger.md](capability-evidence-ledger.md).

The immediate engineering baseline is: findings F01–F18 have implementations and local
regressions in the remediation tree, including evidence/governance repair F10.
PostgreSQL 16/18, exact-candidate artifacts, hosted CI, external deployment, independent
review, and RC observation remain distinct gates. No checked historical milestone or
local result implies those later gates.

> **Verdict: build it.** The product is now narrow enough to execute, internally coherent enough to test, and differentiated enough to justify a separate library.
>
> **FastAPI-Mergen is the transaction boundary for tenant-safe side effects.** It records every deferred effect through the same PostgreSQL transaction as the business change, snapshots the originating principal and route policy, and delivers the effect without silently losing tenant context, obscuring authority provenance, or rewriting retry and replay history.

---

## 0. Audited scorecard

| Dimension | Score | Why the plan earns it |
|---|---:|---|
| **Core thesis** | **9/10** | One boundary problem, seven invariants, and three primitives explain the product. |
| **Market differentiation** | **9/10** | Mergen owns the seam between tenant isolation, the ORM transaction, deferred execution, webhooks, and later delegation rather than replacing incumbents in each category. |
| **Scope discipline** | **9/10** | The Minimum Differentiated Product is frozen. Queue adapters, inbound idempotency, MCP, workflows, ordering, tenant lifecycle, and non-PostgreSQL storage are explicitly post-MDP. |
| **Data model** | **9/10** | Immutable events, independently retryable deliveries, append-only attempts, tenant-safe foreign keys, immutable route/policy snapshots, real dedupe constraints, and unambiguous replay lineage. |
| **Delivery semantics** | **9/10** | Atomic local publication, at-least-once delivery, lease-token compare-and-set, explicit attempt accounting, bounded retry/dead-letter behavior, stale-worker rejection, and testable crash outcomes. |
| **Security architecture** | **9/10** | Fixed trust boundaries, explicit transaction ownership, fail-closed RLS, separate migration/request/relay roles, separate handler sessions, no raw credential persistence, and a concrete SSRF-safe webhook transport. |
| **Packaging strategy** | **9/10** | One distribution, collision-free import and CLI names, `src` layout, narrow public API, optional extras, typed-package marker, compatibility policy, and clean-wheel release tests. |
| **Roadmap realism** | **9/10** | Three gated milestones reach the MDP in 21–26 part-time weeks, include uncertainty reserve and design-partner gates, and postpone every non-essential integration. |
| Technical feasibility | 8.5/10 | The underlying primitives exist, but production safety still depends on disciplined PostgreSQL, SQLAlchemy, concurrency, and network-security implementation. |
| Adoption readiness | 7.5/10 | The wedge is credible, but category education and external deployments have not yet validated demand. |

A **9/10 plan score** means the design is coherent and implementation-ready. It does not claim that production behavior or market demand has already been proved. The final point requires external deployments, adversarial testing, migration experience, and operational history.

---

## 1. Corrections required by the second audit

### 1.1 Scope is frozen at one complete Minimum Differentiated Product

The MDP contains only:

1. trusted `Principal` ingestion and lifecycle;
2. an explicit async SQLAlchemy unit of work;
3. PostgreSQL event, delivery, and attempt persistence;
4. RLS policies, roles, and diagnostics;
5. exact event-type routing with immutable snapshots;
6. a polling, lease-based relay;
7. an in-process async handler sink;
8. signed outbound webhooks;
9. replay, dead-letter operations, metrics, logs, and conformance tests;
10. one production-style reference application.

The following are removed from the first product boundary: queue adapters, inbound HTTP idempotency, MCP/delegation, `LISTEN/NOTIFY`, workflows, timers, cancellation, ordering, tenant provisioning, non-PostgreSQL stores, synchronous SQLAlchemy, and an admin UI.

### 1.2 The transaction model is no longer implicit

For the MDP, `MergenUnitOfWork` owns the outermost `AsyncSession` transaction. It:

- rejects entry when the supplied session is already in a transaction;
- starts the transaction explicitly;
- binds transaction-local tenant context before application SQL;
- exposes `emit()` only through the active unit of work;
- commits or rolls back both application state and effect intents together;
- resets session metadata and `ContextVar` tokens in `finally`.

The first implementation does not rely on global SQLAlchemy event listeners.

### 1.3 The database trust model is fixed

There are exactly three required roles:

- `mergen_migration` owns schema objects and is never a runtime credential;
- `mergen_app` is RLS-restricted to one tenant and is used by request/handler application sessions;
- `mergen_relay` can process all tenants only inside the `fastapi_mergen` schema and has no access to application business tables.

Neither runtime role is a superuser, owns Mergen tables, or has `BYPASSRLS`.

### 1.4 Route and authorization semantics are immutable per delivery

Every original delivery stores:

- `route_key` and `route_version`;
- immutable destination data;
- immutable retry and authorization-policy data;
- the route snapshot schema version;
- stable event and delivery identity.

Later route edits or subscription changes cannot alter committed original deliveries.

### 1.5 Authority must never expand silently

Two user-derived modes are non-expanding:

- `snapshot`: origin scopes intersect route-allowed scopes;
- `revalidate`: current scopes intersect the origin ceiling and route-allowed scopes.

`service_policy` is not represented as user authority. It is an explicit, named service capability configured at startup, with origin subject/actor preserved only for causal audit. The route declaration must make this authority transition visible.

### 1.6 Delivery correctness is polling-first

Polling is authoritative in the MDP. `LISTEN/NOTIFY` is postponed until the polling implementation and crash matrix are stable; when added, notification is only a wake-up hint.

### 1.7 Webhook delivery receives a concrete network-security design

Webhook delivery does not perform a one-time hostname check followed by an ordinary second DNS resolution. The transport resolves and validates destination IPs for every attempt, connects to the validated explicit IP, preserves TLS SNI and HTTP authority for the original hostname, disables redirects by default, and applies strict time, size, concurrency, and address-policy limits.

### 1.8 The calendar is conservative

The first marketable MDP is estimated at **21–26 part-time weeks** at approximately ten hours per week. A production-oriented `v0.5` is more realistically **10–14 months part-time**.

---

## 2. Product thesis

### 2.1 One-sentence definition

> **FastAPI-Mergen makes every deferred effect of a tenant-scoped FastAPI transaction durable, attributable, policy-aware, and safely deliverable.**

### 2.2 Headline promise

> **One commit. Every effect keeps its tenant and authority provenance.**

### 2.3 Boundary problem

```text
 authenticated, tenant-scoped request
                  │
                  ▼
       business database transaction
                  │
       ┌──────────┴───────────┐
       ▼                      ▼
 application state       durable effect intent
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
             internal handler             customer webhook
```

A request may already be authenticated and tenant-isolated, yet correctness can still fail when control leaves the transaction:

- the business row commits but deferred work is not recorded;
- a webhook fires before the transaction rolls back;
- tenant context disappears in a worker;
- a delayed action uses stale, excessive, or unidentified authority;
- one failed destination corrupts another destination’s state;
- a relay crash creates an ambiguous duplicate without a stable ID;
- a replay rewrites history instead of creating an accountable new action.

### 2.4 Seven invariants

For every committed effect, Mergen preserves:

1. **Atomic intent** — application state, event, and original deliveries commit together or not at all.
2. **Tenant continuity** — event, delivery, attempt, and execution context remain bound to one tenant.
3. **Explicit authority provenance** — execution uses attenuated origin authority, revalidated authority, or a named service policy; never an implicit mixture.
4. **Stable retry identity** — automatic retries reuse the same delivery/message identity.
5. **Independent fan-out** — each destination owns its status, attempts, retry clock, and terminal outcome.
6. **Causal lineage** — event, delivery, correlation, causation, actor, client, and trace context remain linked.
7. **Replay accountability** — manual replay creates a new linked delivery and never mutates the original terminal result.

### 2.5 Three primitives

#### `Principal`

Immutable trusted security context containing tenant, subject, optional actor/client, scopes, authentication timestamps, and non-secret references.

#### `Effect`

Immutable typed intent persisted through the application’s database transaction.

#### `Delivery`

One independently retryable route from one effect to one destination.

---

## 3. Market position and differentiation

Mergen is not a tenant manager, queue, webhook SaaS, workflow engine, authentication server, or MCP implementation. It supplies the missing effect-boundary contract between these systems.

| Product class | Tenant isolation | Same ORM transaction | Durable principal/policy | Independent multi-sink state | Authorization freshness | Embedded control plane |
|---|---:|---:|---:|---:|---:|---:|
| FastAPI tenancy package | Yes | No | Runtime context only | No | No common model | Partial |
| Task queue | Usually no | Usually no | Adapter-specific | Tasks only | No common model | Varies |
| PostgreSQL task queue | No | Sometimes | No common principal model | Tasks only | No | Yes |
| Generic outbox/CQRS package | No | Yes | Generic metadata | Usually one handler/broker model | No FastAPI tenant policy | Varies |
| Webhook service | Product-level | Not normally the app ORM transaction | Delivery metadata | Webhooks only | No application authority model | Separate service |
| MCP framework | MCP request identity | No | MCP-specific | MCP only | MCP-specific | No |
| **FastAPI-Mergen** | **Provider-integrated** | **Yes** | **Yes** | **Handlers + webhooks first** | **Snapshot/revalidate/service policy** | **PostgreSQL** |

### 3.1 Defensible wedge

1. Principal information is durable contract data rather than ambient process state.
2. Route and policy are snapshotted per destination rather than re-inferred during retry.
3. The application transaction writes the event and every original delivery intent.
4. Every destination remains operationally independent.
5. The conformance suite tests RLS, authority, lifecycle, and crash invariants.
6. The MDP adds no second mandatory stateful service.
7. Later queue and MCP integrations must implement the same contract rather than create parallel semantics.

### 3.2 Why this is 9/10 rather than 10/10

- the market category still requires explanation;
- components can be copied individually;
- production demand has not yet been established;
- a strong incumbent could adopt the contract;
- the conformance specification may ultimately be more defensible than the runtime.

---

## 4. Scope contract

### 4.1 Minimum Differentiated Product: `v0.2`

The MDP ends after Milestone 3 and contains only:

- immutable `Principal` and provider protocol;
- explicit async SQLAlchemy `MergenUnitOfWork`;
- PostgreSQL event, delivery, and attempt tables;
- Alembic migrations for schema, roles, grants, RLS, and helper functions;
- exact event-type route registry;
- immutable destination and policy snapshots;
- polling relay with leases and bounded retries;
- in-process async handler sink;
- authorization modes `snapshot`, `revalidate`, and explicit `service_policy`;
- signed Standard Webhooks-compatible outbound delivery;
- webhook secret rotation and SSRF-safe transport;
- dead-letter and replay operations;
- metrics, structured logs, diagnostics, conformance tests, and chaos tests;
- one complete invoicing reference application and deduplicating receiver.

### 4.2 Explicitly out of the MDP

- tenant creation, membership, billing, plans, or tenant dashboards;
- schema-per-tenant or database-per-tenant orchestration;
- automatic mutation of arbitrary application ORM models;
- authentication, OAuth, or user management;
- a general-purpose task queue;
- Taskiq, Procrastinate, Celery, or other executor adapters;
- workflows, DAGs, timers, cron, scheduling, human approval, or compensation;
- global or per-key ordering;
- delivery cancellation;
- inbound HTTP idempotency;
- MCP or delegated downstream API access;
- `LISTEN/NOTIFY` optimization;
- hosted control plane or admin UI;
- non-PostgreSQL persistence;
- synchronous SQLAlchemy;
- wildcard event routing or arbitrary subscription expressions;
- automatic partitioning before measured volume requires it.

### 4.3 Feature-admission test

A feature may enter the MDP only when all are true:

1. it enforces one of the seven invariants;
2. it uses the event/delivery/attempt state model rather than a parallel subsystem;
3. it can be represented in the public conformance suite;
4. it adds no second mandatory stateful service;
5. it does not materially widen the database, framework, or executor matrix;
6. removing it would make the first design-partner use case incomplete.

### 4.4 Initial customer profile

- multi-tenant B2B SaaS;
- FastAPI and Pydantic;
- async SQLAlchemy 2.x;
- PostgreSQL;
- internal background handlers and/or customer webhooks;
- meaningful isolation, audit, security, or compliance requirements;
- preference for an embedded library over another operational service.

---

## 5. Guarantee vocabulary

Mergen does **not** promise generic exactly-once distributed execution.

| Boundary | Defensible guarantee |
|---|---|
| Application rows + event + original deliveries | **Atomic local commit** |
| Rolled-back application transaction | **No committed event or original delivery** |
| Delivery execution | **At least once** |
| Consumer-visible outcome | **Effectively once only when the consumer deduplicates the stable delivery/message ID** |
| Fan-out | **Independent state and retry history per destination** |
| Automatic retry | **Same delivery ID; new attempt ID** |
| Manual replay | **New delivery ID linked by `replay_of`** |
| Ordering | **Not guaranteed** |
| Notification | **Optimization only; polling is authoritative** |
| Cancellation | **Not defined in the MDP** |

Recommended public wording:

> **Atomic publication, at-least-once delivery, and first-class stable identities for effectively-once consumers.**

---

## 6. Architecture and trust boundaries

```text
                           FASTAPI REQUEST
                                  │
                    authenticate + select tenant
                                  │
                                  ▼
                         trusted Principal
                                  │
                                  ▼
                     MergenUnitOfWork owns
                    outer SQLAlchemy transaction
                                  │
                    SET LOCAL tenant context
                                  │
                  ┌───────────────┴────────────────┐
                  ▼                                ▼
          application tables               fastapi_mergen.event
                                                    │
                                         fastapi_mergen.delivery
                                                    │
                                                    ▼
                                  relay control-plane connection
                                       role = mergen_relay
                                                    │
                             ┌──────────────────────┴──────────────────────┐
                             ▼                                             ▼
                    in-process handler                               webhook sink
                  fresh tenant-bound app                         outbound safe transport
                         session
```

### 6.1 Trust assumptions

| Component | Trust level | Responsibility |
|---|---|---|
| Authentication/principal provider | Trusted | Validates identity, tenant membership, and conflicting tenant sources before constructing `Principal`. |
| Application process | Trusted but fallible | Bugs are expected; RLS and database constraints contain query mistakes. |
| PostgreSQL and migration role | Trusted | Cluster or migration-owner compromise invalidates the model. |
| Request/handler role | Trusted service credential | Tenant setting is context propagation, not database-native authentication. |
| Relay control-plane process | Trusted but least-privileged | May process all Mergen tenants, but cannot access application business tables. |
| Handler application session | Trusted and tenant-bound | Uses `mergen_app`, not the relay connection, and receives only the execution principal. |
| Tenant input and payload | Untrusted | Validate schema, size, routing data, and identifiers. |
| Webhook URL/receiver | Hostile by default | Apply SSRF, timeout, response-size, redirect, and concurrency controls. |
| Logs/metrics backend | Lower-trust operational sink | Never emit secrets, credentials, or payloads by default. |

### 6.2 Fixed transaction model

For the MDP, `MergenUnitOfWork` owns the outermost transaction:

- entry fails if `AsyncSession.in_transaction()` is true;
- the UoW calls `session.begin()` explicitly;
- it executes transaction-local tenant binding before application queries;
- `emit()` exists only on the active UoW;
- nested Mergen UoWs are rejected;
- application savepoints may be used after tenant binding;
- exit commits on success and rolls back on exception;
- principal context and session metadata reset in `finally`;
- no global SQLAlchemy event listener is required.

### 6.3 Separate relay and handler sessions

The relay uses a `mergen_relay` session only for claiming, reading Mergen-owned rows, renewing leases, writing attempts, and finalizing delivery state.

An in-process handler that needs application data receives a **new tenant-bound `mergen_app` session** through an application-provided handler session factory. The relay connection is never injected into handler code.

---

## 7. Public API

### 7.1 Setup

```python
from fastapi import FastAPI
from fastapi_mergen import Mergen
from fastapi_mergen.postgres import PostgresStore

app = FastAPI()

mergen = Mergen(
    principal_provider=my_principal_provider,
    store=PostgresStore(),
    authorization_resolver=my_authorization_resolver,
)
```

The principal provider must authenticate the request, select an authorized tenant, reject conflicting tenant sources, and return an immutable `Principal`.

### 7.2 Route declaration

```python
mergen.route(
    event_type="invoice.created",
    route_key="invoice.render_pdf",
    version=1,
).to_handler(
    render_invoice_pdf,
    required_scopes={"invoices:read"},
    authorization="revalidate",
    retry_policy="default-handler",
)
```

Rules:

- route keys and versions are explicit;
- registration ends at application startup;
- the registry freezes before requests are accepted;
- MDP matching is exact by `event_type`;
- duplicate key/version definitions fail startup;
- route version downgrades fail startup.

### 7.3 Unit of work and emission

```python
from fastapi import Depends
from fastapi_mergen import Event
from fastapi_mergen.sqlalchemy import MergenUnitOfWork

get_uow = mergen.uow_dependency(get_async_session)


@app.post("/invoices")
async def create_invoice(
    data: InvoiceIn,
    uow: MergenUnitOfWork = Depends(get_uow),
) -> InvoiceOut:
    async with uow:
        invoice = Invoice(
            tenant_id=uow.principal.tenant_id,
            **data.model_dump(),
        )
        uow.session.add(invoice)
        await uow.session.flush()

        await uow.emit(
            Event(
                type="invoice.created",
                version=1,
                data=InvoiceCreated(
                    invoice_id=invoice.id,
                    amount=invoice.amount,
                    currency=invoice.currency,
                ),
            ),
            dedupe_namespace="create-invoice",
            dedupe_key=str(invoice.id),
        )

    return InvoiceOut.model_validate(invoice)
```

Guarantee:

> The invoice row, event, and every original delivery intent commit together—or none of them do.

### 7.4 Handler

```python
from fastapi_mergen import EffectContext


@mergen.handler("invoice.render_pdf", version=1)
async def render_invoice_pdf(
    ctx: EffectContext[InvoiceCreated],
) -> None:
    principal = ctx.principal
    invoice_id = ctx.event.data.invoice_id

    async with ctx.application_session() as session:
        # Session uses mergen_app and is bound to principal.tenant_id.
        ...
```

Handlers are resolved by `route_key` and `route_version`, not a mutable Python function name alone.

### 7.5 Failure classes

Public sink/handler exceptions include:

- `RetryableDeliveryError`;
- `PermanentDeliveryError`;
- `AuthorizationExpired`;
- `AuthorizationDenied`;
- `DedupeConflict`;
- `LeaseLost`;
- `SchemaRevisionMismatch`;
- `MergenConfigurationError`.

Unknown handler exceptions are retryable until policy limits are exhausted; authorization denial is terminal unless an application explicitly maps it otherwise.

---

## 8. Data model

All Mergen-owned tables live in the `fastapi_mergen` schema, include `tenant_id`, use forced RLS, and use tenant-safe composite foreign keys.

### 8.1 Event

```sql
CREATE TABLE fastapi_mergen.event (
    id                       uuid PRIMARY KEY,
    tenant_id                uuid NOT NULL,

    principal_schema_version smallint NOT NULL DEFAULT 1,
    subject_id               text NOT NULL,
    actor_id                 text,
    client_id                text,
    origin_scopes            text[] NOT NULL DEFAULT '{}',
    credential_ref           text,
    principal_issued_at      timestamptz NOT NULL,
    principal_expires_at     timestamptz,
    authentication_time      timestamptz,
    principal_meta           jsonb NOT NULL DEFAULT '{}'::jsonb,

    event_type               text NOT NULL,
    schema_version           integer NOT NULL,
    payload                  jsonb NOT NULL,
    payload_sha256           bytea NOT NULL,

    dedupe_namespace         text,
    dedupe_key               text,

    correlation_id           uuid,
    causation_id             uuid,
    traceparent              text,
    tracestate               text,

    occurred_at              timestamptz NOT NULL,
    created_at               timestamptz NOT NULL DEFAULT statement_timestamp(),

    CHECK (schema_version > 0),
    CHECK (principal_schema_version > 0),
    CHECK (cardinality(origin_scopes) <= 256),
    CHECK ((dedupe_namespace IS NULL) = (dedupe_key IS NULL)),
    UNIQUE (id, tenant_id)
);

CREATE UNIQUE INDEX uq_event_dedupe
    ON fastapi_mergen.event (tenant_id, dedupe_namespace, dedupe_key)
    WHERE dedupe_key IS NOT NULL;

CREATE INDEX ix_event_tenant_created
    ON fastapi_mergen.event (tenant_id, created_at DESC, id);

CREATE INDEX ix_event_type_created
    ON fastapi_mergen.event (event_type, created_at DESC, id);
```

Event rules:

- IDs are application-generated UUIDs; no ordering property is inferred.
- Payloads come from typed DTOs, never arbitrary ORM serialization.
- The payload hash is computed over the library’s versioned canonical JSON representation.
- Dedupe namespace and key are optional but must appear together.
- A dedupe conflict returns the pre-existing event only when tenant, type, schema version, and payload hash match.
- A conflicting payload raises `DedupeConflict`.
- A duplicate emission never creates a second set of original deliveries and never re-routes against a newer registry.
- The principal on the first committed event remains authoritative.

### 8.2 Delivery

```sql
CREATE TABLE fastapi_mergen.delivery (
    id                       uuid PRIMARY KEY,
    tenant_id                uuid NOT NULL,
    event_id                 uuid NOT NULL,

    route_key                text NOT NULL,
    route_version            integer NOT NULL,
    sink_kind                text NOT NULL,
    destination_key          text NOT NULL,
    route_snapshot_version   smallint NOT NULL DEFAULT 1,
    destination_snapshot     jsonb NOT NULL,
    policy_snapshot          jsonb NOT NULL,

    status                   text NOT NULL DEFAULT 'pending',
    attempt_count            integer NOT NULL DEFAULT 0,
    max_attempts             integer NOT NULL,
    next_attempt_at          timestamptz NOT NULL DEFAULT statement_timestamp(),
    delivery_deadline        timestamptz,

    leased_by                text,
    lease_token              uuid,
    lease_until              timestamptz,

    first_attempt_at         timestamptz,
    terminal_at              timestamptz,
    last_error_class         text,
    last_error_code          text,
    last_error_summary       text,

    replay_of                uuid,
    replay_reason            text,
    replayed_by_subject_id   text,

    state_version            bigint NOT NULL DEFAULT 0,
    created_at               timestamptz NOT NULL DEFAULT statement_timestamp(),
    updated_at               timestamptz NOT NULL DEFAULT statement_timestamp(),

    UNIQUE (id, tenant_id),
    FOREIGN KEY (event_id, tenant_id)
        REFERENCES fastapi_mergen.event(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (replay_of, tenant_id)
        REFERENCES fastapi_mergen.delivery(id, tenant_id),

    CHECK (route_version > 0),
    CHECK (route_snapshot_version > 0),
    CHECK (attempt_count >= 0),
    CHECK (max_attempts > 0),
    CHECK (status IN ('pending', 'leased', 'retry_wait', 'succeeded', 'dead')),
    CHECK (
        (status = 'leased' AND leased_by IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL)
        OR
        (status <> 'leased' AND leased_by IS NULL AND lease_token IS NULL AND lease_until IS NULL)
    ),
    CHECK (
        (status IN ('succeeded', 'dead') AND terminal_at IS NOT NULL)
        OR
        (status NOT IN ('succeeded', 'dead') AND terminal_at IS NULL)
    ),
    CHECK (replay_of IS NOT NULL OR replay_reason IS NULL)
);

CREATE UNIQUE INDEX uq_original_delivery_route
    ON fastapi_mergen.delivery (
        event_id,
        route_key,
        route_version,
        destination_key
    )
    WHERE replay_of IS NULL;

CREATE INDEX ix_delivery_due
    ON fastapi_mergen.delivery (next_attempt_at, created_at, id)
    WHERE status IN ('pending', 'retry_wait');

CREATE INDEX ix_delivery_expired_lease
    ON fastapi_mergen.delivery (lease_until, id)
    WHERE status = 'leased';

CREATE INDEX ix_delivery_tenant_status
    ON fastapi_mergen.delivery (tenant_id, status, next_attempt_at, id);

CREATE INDEX ix_delivery_replay_of
    ON fastapi_mergen.delivery (replay_of)
    WHERE replay_of IS NOT NULL;
```

Destination snapshot examples:

```json
{
  "schema": 1,
  "handler_key": "invoice.render_pdf",
  "handler_version": 1
}
```

```json
{
  "schema": 1,
  "subscription_id": "...",
  "endpoint_url": "https://customer.example/hooks",
  "secret_set_id": "..."
}
```

Policy snapshot example:

```json
{
  "schema": 1,
  "authorization": "revalidate",
  "required_scopes": ["invoices:read"],
  "origin_scope_ceiling": ["invoices:read", "invoices:write"],
  "service_policy": null,
  "maximum_snapshot_age_seconds": null,
  "retry_policy": {
    "name": "default-handler",
    "version": 1,
    "max_attempts": 8,
    "maximum_elapsed_seconds": 86400,
    "base_delay_seconds": 2,
    "maximum_delay_seconds": 900,
    "handler_timeout_seconds": 60,
    "lease_duration_seconds": 120
  }
}
```

No raw credential, plaintext webhook secret, or callable object is stored in a snapshot.

### 8.3 Delivery attempt

```sql
CREATE TABLE fastapi_mergen.delivery_attempt (
    id                    uuid PRIMARY KEY,
    tenant_id             uuid NOT NULL,
    delivery_id           uuid NOT NULL,
    attempt_no            integer NOT NULL,
    lease_token           uuid NOT NULL,
    worker_id             text NOT NULL,

    started_at            timestamptz NOT NULL,
    finished_at           timestamptz,
    outcome               text,

    status_code           integer,
    duration_ms           integer,
    bytes_sent            bigint,
    bytes_received        bigint,
    remote_request_id     text,
    retry_after_at        timestamptz,

    error_class           text,
    error_code            text,
    error_summary         text,

    FOREIGN KEY (delivery_id, tenant_id)
        REFERENCES fastapi_mergen.delivery(id, tenant_id) ON DELETE CASCADE,

    UNIQUE (delivery_id, attempt_no),
    CHECK (attempt_no > 0),
    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (bytes_sent IS NULL OR bytes_sent >= 0),
    CHECK (bytes_received IS NULL OR bytes_received >= 0),
    CHECK (
        outcome IS NULL OR outcome IN (
            'succeeded',
            'retryable_failure',
            'terminal_failure',
            'lease_lost',
            'abandoned'
        )
    )
);

CREATE INDEX ix_attempt_delivery_started
    ON fastapi_mergen.delivery_attempt (delivery_id, started_at, attempt_no);

CREATE INDEX ix_attempt_tenant_started
    ON fastapi_mergen.delivery_attempt (tenant_id, started_at DESC, id);
```

`attempt_count` means attempts **started**, not attempts completed. A successful claim increments the count and inserts the attempt row in the same transaction.

### 8.4 Replay

- Automatic retry retains the original delivery ID and creates a new attempt.
- Manual replay creates a new delivery ID with `replay_of` referencing the original tenant-safe delivery key.
- Replay copies the original event, route key/version, destination snapshot, and policy snapshot by default.
- A privileged replay request may explicitly refresh only the policy fields allowed by the application’s replay policy.
- A webhook replay receives a new message ID, intentionally allowing a consumer to process it again.
- The original terminal delivery is never moved back to pending.

### 8.5 Retention

Initial defaults:

- attempts: 30 days;
- succeeded deliveries: 30 days;
- dead deliveries: 90 days;
- events: retained while referenced by a delivery, then configurable;
- payload-body logging: disabled;
- purge order: attempts → deliveries → unreferenced events;
- retention jobs operate in bounded batches;
- partitioning is postponed until measured volume justifies it.

---

## 9. Routing and authorization semantics

### 9.1 Registry

- Routes register before startup completes.
- The registry is frozen before requests are accepted.
- Each route has explicit key and positive integer version.
- Matching is exact by event type.
- A route emits one or more immutable delivery specifications.
- Configuration validation fails before startup when handlers, policies, or retry profiles are unresolved.

### 9.2 Snapshot transaction

Inside `uow.emit()`:

1. validate the typed event DTO;
2. produce canonical bytes and payload hash;
3. resolve exact routes from the frozen registry;
4. query eligible webhook subscriptions for the tenant;
5. build immutable destination and policy snapshots;
6. insert the event or resolve a compatible dedupe hit;
7. insert every original delivery only for a newly inserted event;
8. commit with application rows.

Later route or subscription changes never alter already committed original deliveries.

### 9.3 Authorization modes

#### `snapshot`

Use attenuated scopes captured at emission. A maximum snapshot age is mandatory.

```text
effective_scopes = origin_scopes ∩ route_allowed_scopes
```

#### `revalidate`

Resolve current authorization before each attempt, while preserving the original identity and authority ceiling.

```text
effective_scopes = current_scopes ∩ origin_scope_ceiling ∩ route_allowed_scopes
```

#### `service_policy`

Run as a named application-defined service capability. This is not described as user authority. The execution context retains origin tenant/subject/actor and records the service policy name. Startup validation must resolve the policy and its allowed capabilities.

### 9.4 Authorization failure

- expired snapshot is terminal unless the route explicitly permits revalidation fallback;
- revalidation denial is terminal by default;
- temporary authorization-provider outage is retryable within policy limits;
- an unresolved service policy fails startup, not runtime;
- raw credentials are never stored to support later revalidation.

---

## 10. Delivery state machine

```text
pending ──claim──▶ leased ──success────────────▶ succeeded
                       │
                       ├─retryable failure──────▶ retry_wait ──claim──▶ leased
                       │
                       ├─terminal failure───────▶ dead
                       │
                       └─lease expires──────────▶ reclaimable by new token
```

Terminal rows do not return to pending. Manual replay creates a new row.

### 10.1 Claim transaction

The relay operates at PostgreSQL `READ COMMITTED` isolation.

A claim transaction:

1. selects a selected tenant’s due rows with `FOR UPDATE SKIP LOCKED`;
2. assigns `status='leased'`;
3. creates a fresh `lease_token` and database-time `lease_until`;
4. increments `attempt_count`;
5. sets `first_attempt_at` if null;
6. inserts the append-only attempt row;
7. commits immediately;
8. performs no handler or network I/O while locks are held.

### 10.2 Bounded per-tenant fairness

The MDP promises bounded unfairness, not strict global fairness:

1. select a bounded set of tenants with due work ordered by oldest due delivery;
2. rotate the starting tenant across loops;
3. claim at most `per_tenant_claim_limit` rows per tenant;
4. stop at the worker batch limit;
5. let `SKIP LOCKED` coordinate concurrent workers.

### 10.3 Execution

- Load immutable event and delivery snapshot.
- Reconstruct or revalidate the execution principal.
- For handlers, obtain a fresh tenant-bound application session.
- Apply timeout and payload limits.
- Invoke the sink outside the claim transaction.
- Renew leases through token-checked compare-and-set when execution may exceed half the lease duration.

### 10.4 Finalization

A finalization update succeeds only when:

```text
id = claimed_delivery_id
AND status = 'leased'
AND lease_token = claimed_lease_token
```

Success:

- completes the attempt as `succeeded`;
- sets delivery `succeeded` and `terminal_at`;
- clears lease fields;
- increments `state_version`.

Retryable failure:

- completes the attempt as `retryable_failure`;
- calculates `next_attempt_at` using database time and policy;
- moves to `retry_wait`, or to `dead` when attempts/deadline are exhausted;
- clears lease fields.

Terminal failure:

- completes the attempt as `terminal_failure`;
- sets delivery `dead` and `terminal_at`;
- clears lease fields.

Lease-token mismatch:

- never modifies the current delivery;
- records/reconciles the stale attempt as `lease_lost`;
- increments an operational metric.

### 10.5 Expiry and abandoned attempts

A reconciler finds `status='leased' AND lease_until < statement_timestamp()`.

- The expired delivery is eligible for a new claim.
- A new claim uses a new lease token and attempt number.
- The prior unfinished attempt is marked `abandoned` in the claim or a bounded reconciliation transaction.
- The stale worker cannot finalize because its token no longer matches.

### 10.6 Retry policy

A retry profile contains:

```text
max_attempts
maximum_elapsed_seconds
base_delay_seconds
maximum_delay_seconds
jitter = full
handler_timeout_seconds
lease_duration_seconds
```

Rules:

- full-jitter exponential backoff;
- `Retry-After` may raise the delay but is clamped to policy limits;
- no attempt begins after `delivery_deadline`;
- transient transport failures and timeouts are retryable;
- `PermanentDeliveryError` is terminal;
- unknown handler exceptions are retryable until limits are exhausted;
- deterministic tests inject clock and random sources, while persisted scheduling uses database timestamps.

### 10.7 Graceful shutdown

1. stop selecting tenants;
2. stop claiming deliveries;
3. await active work through a configured grace period;
4. renew only work that is explicitly allowed to finish;
5. otherwise cancel local execution and let the lease expire;
6. close sessions and reset contexts;
7. exit non-zero when an internal invariant is violated.

### 10.8 Polling and notification

Polling is the correctness path through the MDP. After MDP stabilization, `LISTEN/NOTIFY` may be added as a wake-up optimization while periodic polling remains enabled.

---

## 11. Security architecture

### 11.1 Threat model

The conformance and security suites cover:

- malicious tenant-controlled input;
- conflicting tenant sources;
- cross-tenant application query mistakes;
- pooled-connection context leakage;
- table ownership, superuser, `BYPASSRLS`, or grant misconfiguration;
- relay access to application schemas;
- stale workers and lease theft;
- authorization revocation between emission and execution;
- duplicate delivery and replay misuse;
- malicious webhook receivers;
- DNS rebinding, redirects, special-use addresses, and metadata endpoints;
- payload, credential, or secret leakage into logs/metrics/errors;
- unsafe migration/search-path ownership.

### 11.2 PostgreSQL roles

| Role | Owns objects | RLS scope | Grants |
|---|---:|---|---|
| `mergen_migration` | Yes | Administrative | DDL and migration only; never runtime |
| `mergen_app` | No | One bound tenant | Required application/Mergen request operations |
| `mergen_relay` | No | All tenants on Mergen tables only | Claim/read event/delivery, insert/update attempts, update delivery state; no app tables, no delete |

Required conditions:

- runtime roles are not superusers;
- runtime roles have no `BYPASSRLS`;
- runtime roles do not own Mergen or tenant application tables;
- the public schema and search path do not expose unsafe writable objects;
- the relay role has no grants on configured application schemas.

### 11.3 RLS context

Transaction-local tenant binding:

```sql
SELECT pg_catalog.set_config(
    'fastapi_mergen.tenant_id',
    :tenant_id,
    true
);
```

Fail-closed helper:

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

Request-role policy pattern:

```sql
CREATE POLICY event_app_policy
ON fastapi_mergen.event
FOR ALL
TO mergen_app
USING (tenant_id = fastapi_mergen.current_tenant_id())
WITH CHECK (tenant_id = fastapi_mergen.current_tenant_id());
```

Every tenant table has both:

```sql
ALTER TABLE ... ENABLE ROW LEVEL SECURITY;
ALTER TABLE ... FORCE ROW LEVEL SECURITY;
```

Relay policies are separate, explicit, and limited to Mergen-owned tables.

### 11.4 Security limitation

The tenant setting is context propagation, not authentication. A holder of the trusted application database credential can technically bind another tenant. Therefore Mergen protects against query mistakes and missing filters, but not against complete compromise of the application process or its server-side credential.

### 11.5 Principal rules

- immutable model;
- tenant and subject required;
- actor/client optional and explicit;
- scope syntax validated, deduplicated, and bounded;
- raw bearer tokens, cookies, API keys, session tokens, and webhook secrets are never persisted;
- `credential_ref` is opaque and optional;
- conflicting tenant sources fail closed;
- logs reveal only approved identifiers and counts.

### 11.6 `fastapi-mergen doctor`

The command performs live checks for:

- role superuser, owner, and `BYPASSRLS` status;
- required schema/table ownership;
- RLS enabled and forced on each tenant table;
- expected request and relay policies;
- live `USING` and `WITH CHECK` probes;
- request-role cross-tenant denial;
- transaction-local setting reset after commit and rollback;
- pool reuse without prior tenant context;
- relay denial on configured application tables;
- unsafe writable search-path objects;
- package/schema revision compatibility.

### 11.7 Handler session isolation

- control-plane relay session uses `mergen_relay`;
- handler application session uses `mergen_app`;
- tenant binding happens in a fresh handler transaction before application SQL;
- handler dependencies are created and finalized per attempt;
- no request session, relay session, or dependency cache crosses attempts.

### 11.8 Webhook secret management

Milestone 3 introduces `SecretStore` and `MasterKeyProvider` protocols.

Built-in database-backed implementation:

- uses a reviewed cryptography library rather than custom primitives;
- uses AES-256-GCM envelope encryption;
- stores ciphertext, nonce, algorithm, key ID, secret-set ID, and lifecycle state;
- obtains the master key from `MasterKeyProvider`, never PostgreSQL;
- uses one secret set per endpoint;
- supports active and retiring versions during rotation;
- keeps plaintext in bounded process memory only;
- never includes secret material in snapshots, logs, exceptions, or API responses after creation.

### 11.9 SSRF-safe webhook transport

`SafeWebhookTransport` must:

1. require HTTPS in production mode;
2. reject URL credentials and fragments;
3. normalize hostnames with IDNA;
4. resolve all A/AAAA records for every attempt;
5. reject a selected destination when any candidate IP violates the configured global-routing policy;
6. handle IPv4-mapped IPv6 explicitly;
7. connect to a validated explicit IP rather than resolving the hostname again;
8. validate TLS using the original hostname as SNI;
9. send the correct original HTTP authority/Host;
10. disable redirects by default;
11. re-run full validation for every redirect when explicitly enabled;
12. block cloud metadata and other special-use ranges as defense in depth;
13. enforce connect, read, write, pool, and total timeouts;
14. cap request and response bytes;
15. apply global, tenant, and destination concurrency limits;
16. use a trusted egress proxy only in an explicit deployment mode.

### 11.10 Data minimization

- typed payload DTOs only;
- initial payload maximum: 256 KiB, configurable downward;
- no webhook response bodies persisted by default;
- bounded, control-character-cleaned error summaries;
- no payloads or secrets in metrics;
- structured-log redaction hooks;
- configurable retention with safe defaults;
- replay and secret rotation actions are auditable.

---

## 12. Webhook MDP semantics

### 12.1 Subscription model

A tenant subscription contains:

- stable subscription ID;
- exact event-type set;
- endpoint URL;
- stable secret-set ID;
- status `active`, `paused`, or `disabled`;
- retry-profile name/version;
- created/updated/audit identifiers;
- consecutive-failure counter and auto-pause threshold.

A pause affects **future route snapshotting**. Existing committed deliveries retain their immutable intent and continue under their snapshotted retry policy unless an operator explicitly performs a separately audited dead-letter action. MDP cancellation is not implied by pause.

### 12.2 Wire envelope

A versioned webhook envelope contains at least:

```json
{
  "specversion": "1",
  "id": "stable-delivery-message-id",
  "event_id": "origin-event-id",
  "type": "invoice.created",
  "schema_version": 1,
  "tenant_id": "tenant-id",
  "occurred_at": "2026-08-24T00:00:00Z",
  "data": {}
}
```

Rules:

- envelope bytes are deterministic for one delivery;
- automatic retry keeps the same envelope and message ID;
- attempt timestamp and signatures may change;
- manual replay creates a new delivery/message ID;
- the exact bytes signed are the exact bytes sent.

### 12.3 Signing and rotation

- use Standard Webhooks-compatible headers and signing behavior;
- automatic retries retain the stable message ID;
- active and retiring secret versions may both sign during overlap;
- receiver examples verify all supplied signatures and accept any currently trusted version;
- secret rotation does not mutate the destination snapshot;
- revocation and deletion are separate, audited lifecycle operations.

### 12.4 Failure classification

Retryable by default:

- network timeout/reset;
- DNS or connect failure not caused by blocked-address policy;
- HTTP `408`, `425`, `429`, and `5xx` unless explicitly overridden;
- temporary signing/key-provider failure.

Terminal by default:

- invalid or blocked URL;
- TLS hostname/certificate failure;
- body exceeds configured limit;
- HTTP status explicitly configured as permanent;
- missing or irrecoverable secret material.

`Retry-After` may postpone the next attempt but is clamped by retry policy and delivery deadline.

### 12.5 Auto-pause

- consecutive failures are tracked at subscription level;
- success resets the consecutive-failure counter;
- crossing the configured threshold marks the subscription paused for new events;
- auto-pause emits an auditable operational event and metric;
- existing deliveries are not silently cancelled;
- reactivation is an explicit authenticated operation.

---

## 13. Packaging and repository strategy

### 13.1 One distribution

```text
pip install fastapi-mergen
pip install "fastapi-mergen[webhooks]"
pip install "fastapi-mergen[otel]"
```

Post-MDP extras may include `taskiq`, `fastmcp`, or additional DBAPI drivers only when those integrations exist.

### 13.2 Import and CLI

```python
import fastapi_mergen
```

The top-level `mergen` import is not used because it is already occupied by another Python distribution.

```text
fastapi-mergen doctor
fastapi-mergen schema check
fastapi-mergen relay run
```

### 13.3 Dependency boundary

Base dependencies:

- FastAPI/Pydantic supported generation;
- SQLAlchemy 2.x async;
- Alembic;
- a canonical JSON dependency only if the internal implementation cannot meet the test vectors cleanly.

`webhooks` extra:

- HTTPX;
- Standard Webhooks implementation;
- `cryptography`.

`otel` extra:

- OpenTelemetry API and selected integration packages.

The application selects the PostgreSQL async DBAPI. The first certified driver is `asyncpg`; async psycopg certification is a later compatibility task, not an MDP promise.

### 13.4 Repository layout

```text
fastapi-mergen/
├── pyproject.toml
├── README.md
├── LICENSE
├── SECURITY.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── uv.lock
├── docs/
│   ├── index.md
│   ├── concepts/
│   │   ├── boundary-contract.md
│   │   ├── guarantees.md
│   │   ├── authorization.md
│   │   └── threat-model.md
│   ├── operations/
│   │   ├── roles-and-rls.md
│   │   ├── relay.md
│   │   ├── retries-and-replay.md
│   │   ├── webhooks.md
│   │   └── retention.md
│   ├── reference/
│   └── adr/
├── src/fastapi_mergen/
│   ├── __init__.py
│   ├── py.typed
│   ├── api.py
│   ├── errors.py
│   ├── core/
│   │   ├── principal.py
│   │   ├── context.py
│   │   ├── event.py
│   │   ├── delivery.py
│   │   ├── routing.py
│   │   ├── policy.py
│   │   ├── retry.py
│   │   └── protocols.py
│   ├── sqlalchemy/
│   │   ├── uow.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   └── canonical.py
│   ├── postgres/
│   │   ├── rls.py
│   │   ├── roles.py
│   │   ├── leasing.py
│   │   ├── relay.py
│   │   ├── diagnostics.py
│   │   └── migrations/
│   ├── handlers/
│   │   ├── registry.py
│   │   ├── executor.py
│   │   └── dependencies.py
│   ├── webhooks/
│   │   ├── models.py
│   │   ├── subscriptions.py
│   │   ├── serializer.py
│   │   ├── signing.py
│   │   ├── secrets.py
│   │   ├── transport.py
│   │   ├── sink.py
│   │   └── api.py
│   ├── observability/
│   ├── conformance/
│   ├── testing/
│   └── cli/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── conformance/
│   ├── chaos/
│   ├── security/
│   └── packaging/
├── examples/
│   ├── invoicing/
│   └── webhook_receiver/
└── .github/workflows/
```

### 13.5 Public API policy

Root exports remain small:

```text
Mergen
Principal
Event
EffectContext
MergenUnitOfWork
AuthorizationMode
RetryPolicy
selected public exceptions
```

Public symbols are declared in `api.py`, re-exported from `__init__.py`, documented, and covered by import tests. Internal module paths are not automatically compatibility commitments.

### 13.6 Compatibility matrix

Initial certified matrix:

- Python 3.11–3.14;
- SQLAlchemy 2.0 release line;
- supported current FastAPI/Pydantic generation;
- PostgreSQL 16–18;
- async SQLAlchemy only;
- `asyncpg` reference driver.

CI includes:

- unit tests on all supported Python versions;
- pairwise PostgreSQL coverage rather than a full Cartesian matrix;
- minimum dependency job;
- latest dependency job;
- clean sdist/wheel install jobs;
- migration upgrade/downgrade job;
- import-without-extras job;
- optional-extra isolation jobs;
- type checking, linting, formatting, and security checks.

### 13.7 Release discipline

- semantic versioning;
- pre-1.0 changes remain documented and migration-aware;
- schema revisions are compatibility-gated;
- no runtime auto-migration;
- startup checks schema compatibility and emits an actionable diagnostic;
- releases build and test both sdist and wheel;
- PyPI publication uses trusted publishing/OIDC;
- no second distribution before user evidence proves an independent release/dependency boundary.

---

## 14. Conformance and quality strategy

### 14.1 Atomicity

- commit creates application row, event, and every original delivery;
- rollback creates none;
- `emit()` outside active UoW fails;
- session already in a transaction fails at UoW entry;
- dedupe races converge to one event and one original delivery set;
- dedupe payload mismatch fails explicitly.

### 14.2 Isolation

- tenant A cannot select, insert, update, or delete tenant B Mergen rows;
- missing tenant context is default-deny;
- both `USING` and `WITH CHECK` behavior is tested;
- table-owner, superuser, and `BYPASSRLS` misconfiguration fails diagnostics;
- pooled connections do not retain tenant context;
- relay role cannot access configured application tables;
- handler application sessions are tenant-bound and separate from relay sessions.

### 14.3 Authority

- snapshot and revalidate modes cannot expand origin authority;
- snapshot maximum age is enforced;
- revalidation observes revocation;
- service policy is explicit and distinguishable from user authority;
- unresolved service policy fails startup;
- raw credentials never enter rows, logs, metrics, or exceptions.

### 14.4 Delivery

- crash before execution safely retries;
- crash after remote success retries the same stable delivery ID;
- stale finalization cannot overwrite a reclaimed lease;
- lease renewal is token-checked;
- one destination failure does not modify another;
- attempts are append-only;
- attempt number increments at claim;
- manual replay creates a new linked delivery;
- terminal rows never silently return to pending.

### 14.5 Lifecycle

- principal context resets on success, failure, and cancellation;
- request, relay, and handler sessions are closed or returned cleanly;
- yielded handler dependencies finalize per attempt;
- shutdown stops claims before active work termination;
- abandoned attempts are reconciled without corrupting a newer lease.

### 14.6 Webhooks

- Standard Webhooks test vectors pass;
- signed bytes equal sent bytes;
- retries retain stable message identity;
- replay creates new message identity;
- overlapping signatures support rotation;
- `Retry-After` classification is deterministic;
- redirects are disabled by default;
- blocked-address, mapped-address, redirect, and DNS-rebinding cases fail;
- response bodies are not persisted by default;
- reference consumer produces one effective outcome after duplicate attempts.

### 14.7 Packaging

- base package imports without webhook/OTel extras;
- extras do not leak into base dependencies;
- sdist and wheel produce equivalent behavior;
- `py.typed` is present in built artifacts;
- public API import contract is tested;
- console command does not collide with the occupied `mergen` name;
- migration package data exists in the wheel.

---

## 15. Roadmap

Assumption: solo, part-time, approximately ten hours per week. Estimates include a 20–25% uncertainty reserve. Exit gates take precedence over calendar targets.

### Milestone 1 — Specification and repository foundation

**Duration:** 3–4 weeks  
**Effort:** 30–40 hours  
**Release:** internal `0.0.x`; no public product claim

Deliver:

- Boundary Contract v0.1;
- guarantee vocabulary;
- threat and trust model;
- ADR set for transaction, data, routing, authorization, roles, and leases;
- frozen MDP scope;
- repository, packaging, lint/type/test tooling, and CI skeleton;
- narrow public API spike;
- PostgreSQL integration-test environment;
- invoicing reference-app skeleton.

Exit gate:

- no unresolved ambiguity in event/delivery identity, route snapshots, dedupe, replay, RLS trust, authorization modes, or lease behavior;
- clean wheel installs and imports with and without extras;
- architecture review checklist passes;
- estimated M2/M3 tasks fit the frozen scope and effort envelope.

### Milestone 2 — Core transactional effect engine

**Duration:** 10–12 weeks  
**Effort:** 100–130 hours  
**Release:** limited `v0.1.0a1`

Deliver:

- immutable core models and context lifecycle;
- explicit SQLAlchemy UoW;
- event/delivery/attempt schema;
- Alembic role, grant, RLS, and policy migrations;
- event dedupe behavior;
- exact route registry and immutable snapshots;
- polling relay;
- lease-token claim, finalize, renewal, and reconciliation;
- retry policy and dead-letter state;
- bounded per-tenant fairness;
- in-process handler sink with separate app sessions;
- snapshot/revalidate/service-policy authorization;
- `fastapi-mergen doctor`;
- atomicity, isolation, authority, lifecycle, delivery, and packaging conformance suites;
- crash harness and invoicing vertical slice.

Exit gate:

- all core suites pass against PostgreSQL 16 and 18;
- kill-at-each-boundary chaos matrix shows no lost committed delivery;
- stale workers cannot finalize reclaimed work;
- two tenants and sequential/concurrent handlers show no principal, dependency, or session leakage;
- relay role cannot access application business tables;
- at least one external design partner accepts the API/schema for serious evaluation.

### Milestone 3 — Webhook Minimum Differentiated Product

**Duration:** 8–10 weeks  
**Effort:** 80–110 hours  
**Release:** `v0.2.0b1`, then `v0.2.0` after design-partner validation

Deliver:

- subscription and encrypted secret tables;
- exact event-type subscription filters;
- immutable webhook route snapshots;
- deterministic wire serialization;
- Standard Webhooks signing;
- zero-downtime secret rotation;
- SSRF-safe explicit-IP transport;
- webhook failure classification and `Retry-After` support;
- retries, dead-letter, replay, and endpoint auto-pause;
- tenant-scoped operational API;
- metrics, structured logs, and audit events;
- deduplicating reference receiver;
- webhook security/conformance/chaos suite;
- production-style demo and operations documentation.

Exit gate:

- a design partner runs the full flow in serious staging or production-like conditions;
- receiver-success/relay-crash produces multiple attempts and one effective consumer outcome;
- SSRF suite blocks private, loopback, link-local, metadata, mapped-address, redirect, and DNS-rebinding cases;
- rotation works with overlapping signatures;
- pausing affects future snapshotting without mutating committed deliveries;
- no payload or secret leaks in logs, metrics, errors, API responses, or attempt rows.

### Milestone 4 — Existing executor adapter

**Duration:** 5–7 weeks  
**Release:** `v0.3.0`

Taskiq first. Add one PostgreSQL-native executor only after user demand. Do not build a generic queue framework.

### Milestone 5 — Transactional command idempotency

**Duration:** 4–6 weeks  
**Release:** `v0.4.0`

Unit-of-work-bound command idempotency, not superficial response caching.

### Milestone 6 — Delegation and FastMCP integration

**Duration:** 5–7 weeks  
**Release:** `v0.5.0`

Build only after a concrete user requires audience-bound, scope-attenuated delegated access.

### Calendar expectation

- first limited alpha: approximately 3.5–4 months part-time;
- first marketable MDP: approximately 5–6 months part-time;
- production-oriented `v0.5`: approximately 10–14 months part-time;
- `v1.0`: only after at least two external production deployments, a stable migration story, and documented operational history.

---

## 16. Go-to-market gates

### Before Milestone 2 completes

- interview at least five target engineering teams;
- recruit at least two design partners;
- validate terminology against their incident histories;
- test whether “tenant-safe effects” communicates the category;
- publish the Boundary Contract independently of the runtime.

### Before public `v0.2`

- one complete production-style reference deployment;
- one design partner using serious staging or production-like data/traffic;
- public security model and support matrix;
- reference article on async FastAPI, SQLAlchemy, RLS, pooling, and deferred effects;
- documented migration, backup, restore, relay, and incident procedures.

### Continue past `v0.2` only when

At least one of the following is true:

- an external production deployment exists;
- two external applications run the relay in serious staging;
- a design partner requests the first queue adapter;
- a concrete user requires transactional command idempotency or delegated MCP/API calls.

Stars are not a primary continuation metric.

---

## 17. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---:|---|
| Category requires education | High | Boundary Contract, reference application, incident-oriented documentation |
| Security scope exceeds solo capacity | High | Frozen MDP, conservative milestones, external review before public beta |
| Product expands into workflows | High | Feature-admission test; no DAG, timer, order, or cancellation semantics |
| RLS gives false confidence | High | Explicit threat limitation, doctor probes, role separation, FORCE RLS, conformance tests |
| Relay role becomes overprivileged | High | Dedicated schema grants; no app-table grants; live denial tests |
| Handler accidentally uses relay session | High | Separate session protocol; no relay session in handler context; tests |
| Webhook SSRF implementation is incomplete | High | Explicit-IP transport, adversarial suite, production egress controls |
| Duplicate side effects surprise users | High | At-least-once language, stable IDs, receiver dedupe example, crash demo |
| Route mutation changes pending work | Medium | Immutable destination/policy snapshots |
| Secret rotation changes signatures across attempts | Medium | Stable body/message ID, per-attempt timestamp/signature, overlap documentation |
| Database volume grows unexpectedly | Medium | Retention defaults, bounded purge, metrics; partition only after evidence |
| Packaging surface fragments | Medium | One distribution through MDP; extras only |
| Schedule slips | Medium | Effort reserve, milestone gates, no integration work before MDP |
| Incumbent adopts the contract | Medium | Open conformance spec, execution quality, integrations after demand |

---

## 18. Kill and pivot criteria

### Before deep implementation

Stop or radically narrow when five customer interviews reveal no recurring incident involving transactional side effects, tenant context, webhook reliability, or deferred authorization.

### After Milestone 2

Stop at a reusable internal RLS/outbox component when no design partner accepts the API and schema for serious evaluation.

### After Milestone 3

Stop before queue, idempotency, or MCP work when no third party runs the MDP in serious staging or production-like conditions within twelve weeks of public beta.

### Pivot

When users value the conformance/diagnostic layer more than the runtime, pivot toward the **Mergen Boundary Contract and Assurance Suite** rather than expanding into orchestration.

---

## 19. Frozen decisions before coding

1. MIT licence.
2. PostgreSQL only through the MDP.
3. Async SQLAlchemy only.
4. `asyncpg` is the first certified driver.
5. One distribution: `fastapi-mergen`.
6. Import package: `fastapi_mergen`.
7. CLI: `fastapi-mergen`.
8. `src` layout and `py.typed` marker.
9. Mergen UoW owns the outer transaction.
10. No global SQLAlchemy listener in the first implementation.
11. Request, relay, and migration roles are separate.
12. Relay connection never enters handler code.
13. Forced RLS and both `USING`/`WITH CHECK` are required.
14. Event, delivery, and attempt are separate tables.
15. Route/destination/policy snapshots are immutable.
16. Dedupe is tenant + namespace + key, with payload conflict detection.
17. Automatic retry reuses a delivery ID; replay creates a new one.
18. Delivery guarantee is at least once.
19. Polling is authoritative through the MDP.
20. State machine excludes cancellation and ordering.
21. Exact event-type routing only.
22. `snapshot`, `revalidate`, and explicit `service_policy` are the only authorization modes.
23. Webhook transport is HTTPS-first and SSRF-safe by construction.
24. Queue adapters, inbound idempotency, and delegation are post-MDP.
25. No second distribution before evidence of an independent release boundary.
26. `v1.0` requires external production deployments and operational history.

---

## 20. Final assessment

The plan now honestly reaches **9/10** in all requested design dimensions:

- the core thesis names one boundary problem;
- market differentiation rests on an integrated contract rather than isolated features;
- scope ends at one complete and demonstrable MDP;
- the data model can represent independent fan-out, retry, dedupe, and replay without overloading one row;
- delivery guarantees match distributed-systems reality;
- security boundaries are fixed rather than left as implementation options;
- packaging minimizes release and namespace risk;
- the roadmap reflects the cost of migrations, crash testing, security work, documentation, and external validation.

The correct next step is Milestone 1, not implementation of individual features. The accompanying technical checklist converts the first three milestones into file-level tasks with explicit completion criteria.

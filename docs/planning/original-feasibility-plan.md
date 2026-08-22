# Mergen — Feasibility Check and Build Plan

**Date:** 2026-08-23 · **Status:** pre-alpha, no code written · **Working name:** Mergen (`fastapi-mergen` on PyPI, free; bare `mergen` taken by a dormant 2020 astronomy package)

**Verdict: build it — but at materially different scope than originally sketched.** Two of the four pillars survived verification intact, one was overstated, and one should be downgraded from "build a library" to "ship an integration." The good news is that the correction makes the project *smaller* and its thesis *sharper*.

---

## 0. What changed after checking

| Original claim | What verification found | Revised |
|---|---|---|
| Multi-tenancy for FastAPI is an empty field | **Confirmed, and stronger than claimed.** ~9 competing solo packages; the largest has **4 stars**. Zero third-party writeups for any of them. Django's incumbent `django-tenants` has **1.9k stars and shipped three releases in August 2026** — proving demand exists and that FastAPI simply lacks the equivalent | **Keep. This is the core.** |
| "FastAPI DI-aware jobs" is a gap | **Overstated.** `taskiq` (2.2k★, released 2026-08-21) genuinely supports literal `fastapi.Depends()` in tasks — nested deps, `yield` deps with correct teardown, all verified by running it. Transactional enqueue is likewise solved by `procrastinate` (3.8.0, 2026-04-06) and `pgqueuer` | **Narrow it.** The gap is the *intersection*: no library has DI **and** transactional enqueue **and** context propagation. And no credible Python transactional-outbox library exists at all — the highest-starred attempt has 19 stars and died in 2022 |
| Build the jobs layer | Writing a ninth task queue would be suicide | **Don't build a queue. Build the outbox**, and treat "run a job" as one sink |
| Webhook delivery is a gap | **Confirmed for embeddable Python.** No `pip install`-able outbound delivery engine exists for FastAPI. The only Python-ecosystem attempt, `django-webhook` (225★), is Django-locked and stale since 2024-08-19 | **Keep**, with a competitive caveat I originally missed (below) |
| Build MCP exposure; fastapi-mcp's auth is thin | **Wrong target.** `fastapi-mcp` (11.9k★) is effectively **dead** — last release 2025-07-28, pinned to the `mcp` 1.x line, cannot speak the current 2026-07-28 spec. The live incumbent is **FastMCP** (27.3k★, PrefectHQ-backed, v3.4.7 on 2026-08-10), which already does `from_fastapi()` projection *and* per-caller scope-filtered tool listing | **Downgrade to an integration**, aimed at the one thing FastMCP does *not* solve (below) |
| Mergen "sits above fastapi-users" the way fastapi-users sits above SQLAlchemy | `fastapi-users` (6.2k★, v15.0.5 on 2026-03-27) is in **maintenance mode** — maintainers state no new features will be added and are building a successor | **Reframe.** Depend on no specific auth library; accept a `Principal` from any of them. Also a risk to watch: that successor could expand into org/tenancy territory |

### The one finding that reshapes the pitch

FastMCP's `from_fastapi()` bridges into your app via an in-process ASGI transport, but `get_http_headers()` **strips the `authorization` header by default**. The common workaround is to put a single static service token on the internal HTTP client — which means **every tenant's agent reaches your API as one shared privileged identity**. That is a textbook confused-deputy vulnerability, and it is the default outcome of the most popular way to do this today.

Mergen's whole reason for existing — identity and tenant surviving a boundary crossing — is the fix. That reframes the MCP pillar from "expose your API to agents" (solved, crowded, commoditizing fast) to **"don't turn your API into a confused deputy when you do"** (unsolved, and a security story rather than a convenience story).

---

## 1. Thesis

All four pillars are **boundary crossings where the caller's tenant and identity must survive, exactly once**.

```
   HTTP request ──▶ database        tenant isolation (RLS)
   HTTP request ──▶ background job  context must travel with the work
   business txn ──▶ outbound call   must not fire on a rolled-back transaction
   agent (MCP)  ──▶ HTTP request    must not collapse into one shared identity
```

Two primitives cover all four:

1. **`Principal`** — `(tenant_id, actor_id, scopes)` resolved once at the edge, carried in a `contextvar`, enforced at the data layer, and serialized into anything outbound.
2. **The outbox** — a durable intent row written *in the same transaction* as the business change, then delivered by a dispatcher with retries, backoff, idempotency and a dead-letter queue.

Jobs and webhooks are not two subsystems. They are one outbox with two sinks.

---

## 2. Scope: build vs. depend

Being disciplined here is what keeps a four-pillar project from becoming an unmaintainable kitchen sink.

**Build (this is the actual product):**

- Tenant/principal resolution and contextvar propagation
- Postgres RLS integration for **async** SQLAlchemy 2.0, including policy DDL generation and Alembic ops
- The outbox table, `emit()`, and the dispatcher/relay
- Webhook sink: subscriptions, delivery attempts, DLQ, replay, delivery-log endpoints
- Inbound idempotency middleware
- Context propagation adapters into existing queues

**Depend on, never reimplement:**

| Need | Use | Why |
|---|---|---|
| Signing | `standardwebhooks` 1.1.0 | The de-facto spec; even Svix's own client depends on it now |
| DI inside workers | `fastapi-injectable` (295★, v1.6.1 on 2026-08-20) | Makes real `Depends()` work outside FastAPI. Caveat: process-global dependency cache — needs per-job scoping or you leak connections |
| Job execution | adapters for `taskiq` / `procrastinate` / `pgqueuer` / Celery | Play nicely with incumbents. `arq` is **maintenance-only** since Oct 2025 — do not target it |
| MCP protocol | `fastmcp` | 27k stars and a weekly release cadence. Competing is not an option |
| Auth | nothing | Adapter function producing a `Principal`. Works with fastapi-users, Authlib, WorkOS, Clerk, PropelAuth |

**Explicitly out of scope:** an auth/user system, an admin UI, billing, a task queue, an MCP server implementation.

### Why owning the outbox table dodges the hard problem

The obvious approach — hand a queue library your transaction — runs straight into driver friction: `procrastinate`'s only SQLAlchemy connector is **psycopg2, sync only**; `pgqueuer` has no SQLAlchemy driver at all; `taskiq`'s `kick()` accepts no connection and *structurally cannot* join your transaction without forking a broker.

If the outbox is **your own table, written through the user's own async SQLAlchemy session**, transactionality is free and ORM-native, with no raw-connection gymnastics. The relay then dispatches to whatever executor the user already runs. Mergen becomes complementary to every queue instead of competing with all of them.

---

## 3. Architecture

```
                    ┌───────────────────────────┐
   request ────────▶│  resolve → Principal      │  header / subdomain / JWT / API key
                    │  (contextvar)             │
                    └────────────┬──────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
      RLS-bound session    emit() → outbox     scope enforcement
      (SET LOCAL)          (same txn)          (@requires)
                                 │
                                 ▼
                        ┌────────────────┐
                        │    relay       │  FOR UPDATE SKIP LOCKED + LISTEN/NOTIFY
                        └───┬────┬───┬───┘
                            │    │   │
              task sink ◀───┘    │   └──▶ audit sink
                                 ▼
                          webhook sink   signed, retried, DLQ'd, per-tenant
```

### Packages

Distributions all prefixed `fastapi-mergen-*`, importing under one `mergen.*` root:

| Distribution | Import | Contents | Depends on |
|---|---|---|---|
| `fastapi-mergen` | `mergen` | `Principal`, resolvers, contextvar, scopes, `@requires` | fastapi, pydantic |
| `fastapi-mergen-sqlalchemy` | `mergen.sa` | RLS session, policy DDL, Alembic ops, outbox table | + sqlalchemy, alembic |
| `fastapi-mergen-tasks` | `mergen.tasks` | task sink, executor adapters, DI in workers | + fastapi-injectable |
| `fastapi-mergen-webhooks` | `mergen.webhooks` | subscriptions, signing, delivery, DLQ, replay | + httpx, standardwebhooks |
| `fastapi-mergen-mcp` | `mergen.mcp` | identity forwarding, scope→tag mapping, quotas, audit | + fastmcp |

Core must stay small enough to read in one sitting. Each package usable alone. `pip install fastapi-mergen[tasks,webhooks,mcp]` for everything.

---

## 4. API sketch

```python
from mergen import Mergen, Principal, requires, emit

mergen = Mergen(
    resolve=SubdomainResolver() | HeaderResolver("X-Org") | JWTClaimResolver("org_id"),
    principal_from=my_auth_adapter,  # bring your own auth
    isolation="rls",  # or "filter" / "schema"
)
app.add_middleware(mergen.middleware)


@app.post("/invoices", operation_id="create_invoice", tags=["mcp"])
@requires("invoices:write")
async def create_invoice(data: InvoiceIn, db: AsyncSession = Depends(mergen.session)):
    inv = Invoice(**data.model_dump())  # tenant_id applied automatically
    db.add(inv)
    await emit("invoice.created", inv, sinks=["task", "webhook"])
    return inv  # one commit — row, job and webhook, or none
```

```python
@mergen.task(retries=5, backoff="exponential")
async def render_pdf(invoice_id: UUID, storage: Storage = Depends(get_storage)):
    p = Principal.current()  # tenant restored, not passed by hand
    ...
```

```python
mcp = mergen.mcp(app, include=lambda r: "mcp" in r.tags)
# per-caller token → Principal → scopes → filtered tool list
# → forwarded downstream as that tenant, not as a shared service account
```

The demo that sells it: **one `emit()`, three destinations, one transaction, every hop tenant-scoped.**

---

## 5. Data model

```sql
CREATE TABLE mergen_outbox (
  id            bigserial PRIMARY KEY,
  tenant_id     uuid NOT NULL,
  actor_id      uuid,
  event_type    text NOT NULL,
  payload       jsonb NOT NULL,
  sinks         text[] NOT NULL,
  dedupe_key    text,                       -- UNIQUE (tenant_id, dedupe_key)
  available_at  timestamptz NOT NULL DEFAULT now(),
  attempts      int NOT NULL DEFAULT 0,
  status        text NOT NULL DEFAULT 'pending',   -- pending|in_flight|done|dead
  trace_id      text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON mergen_outbox (status, available_at) WHERE status = 'pending';
```

Plus `mergen_subscription` (tenant, url, secret, event filter, active), `mergen_delivery` (attempt log: status code, duration, response snippet, next retry), and `mergen_idempotency` (tenant, key, request fingerprint, cached response, expires).

Design notes: the relay uses `FOR UPDATE SKIP LOCKED` with `LISTEN/NOTIFY` for low latency; secrets are encrypted at rest with a key from app config; delivery bodies are truncated and PII-scrubbed before logging.

**Inbound idempotency is worth shipping early as a standalone teaser.** It is a small, clean, genuinely unfilled gap: `asgi-idempotency-header` has been dead since 2022, the Django equivalent since 2023, and the newest attempt has 1 star. Note that the IETF `Idempotency-Key` draft **expired 2025-10-15** — follow Stripe's convention, which is the real standard, and say so in the docs.

---

## 6. Roadmap

Assumes solo, part-time (~10 h/week). Halve the calendar if full-time.

### Phase 0 — Core + RLS (3–4 weeks) → `v0.1`
`Principal`, resolvers, contextvar, `@requires`. RLS session with `set_config(..., true)`, a `begin` listener so the GUC survives nested transactions, and listener removal in `finally` to prevent pool leakage. Policy DDL generation and Alembic ops. A non-`BYPASSRLS` role check that fails loudly at startup.

*Exit criteria:* a cross-tenant leak test suite that fails on every isolation mode when tenancy is bypassed; docs that beat the 2022 blog post everyone currently copies.

### Phase 1 — Outbox + tasks (4–6 weeks) → `v0.2`
Outbox table, `emit()`, relay with SKIP LOCKED + NOTIFY, retries/backoff/DLQ. Task sink with context restore. Executor adapters (in-process worker first, then taskiq and procrastinate). DI via `fastapi-injectable` with per-job scope discipline.

*Exit criteria:* chaos test — kill the relay mid-delivery, assert exactly-once effect; assert no job ever fires for a rolled-back transaction.

### Phase 1.5 — Idempotency middleware (1 week) → separate release
Small, standalone, shippable on its own. Use it to test whether anyone is listening before committing to Phase 2.

### Phase 2 — Webhooks (4–5 weeks) → `v0.3`
Subscription CRUD, `standardwebhooks` signing, delivery attempts, DLQ, replay endpoint, per-tenant delivery log API, SSRF protection on subscriber URLs (this matters — customers supply those URLs).

*Exit criteria:* a live demo where a customer registers an endpoint, receives signed events, the endpoint fails, and delivery recovers visibly.

### Phase 3 — MCP (2–3 weeks) → `v0.4`
Identity forwarding that fixes the confused deputy. Route scopes → `mcp_tags` → `restrict_tag` mapping so tool visibility is per-caller by construction. Per-tenant quotas via FastMCP's rate-limiting middleware `get_client_id` hook. Idempotency keys for agent-initiated writes — an outright gap in the spec, where `idempotentHint` is explicitly advisory and untrusted. Identity-linked audit trail.

**Ship last, lead the README with it.** Highest attention, thinnest code, highest commoditization risk.

Total to `v0.4`: roughly **4–5 months part-time**.

---

## 7. Go-to-market — the actually hard part

The research is unambiguous that code is not the bottleneck. Eight or nine people have written FastAPI tenancy packages in 2026 alone; the best-resourced has 4 stars and zero third-party mentions. **Assume execution and distribution are the whole game.**

1. **Own the reference article.** The canonical resource for multi-tenant FastAPI is still a **May 2022 blog post using sync SQLAlchemy 1.x**. Write the 2026 async version — RLS, connection pooling, the `BYPASSRLS` trap, Alembic — as documentation first and marketing second. This is the single highest-leverage move available.
2. **Answer [FastAPI discussion #6056](https://github.com/fastapi/fastapi/discussions/6056)**, the canonical unanswered multi-tenancy thread — four replies, no library recommended, still ranking.
3. **Lead with the confused-deputy finding.** "Your MCP integration is probably giving every tenant's agent the same privileged identity" is a security disclosure that travels far further than a feature list.
4. Ship one thing that works completely before announcing anything. PR into `awesome-fastapi`; Show HN once Phase 2 lands; pitch Python Bytes / Talk Python.
5. **Target: 3 real production users by month 6.** Not stars.

---

## 8. Risks and kill criteria

| Risk | Severity | Mitigation |
|---|---|---|
| Adoption, not code, is the constraint — proven by 9 failed attempts | **High** | Docs-first strategy above; win on execution, not novelty |
| Maintenance surface: 4 subsystems, 1 person | **High** | Strict scope discipline; depend rather than build; ship phases as independently useful packages |
| FastMCP commoditizes the MCP pillar within 12 months | **High** | Keep it thin and last. Its value is the identity fix, not the projection |
| Hookdeck Outpost (Apache-2.0, GA April 2026, real parity, $10/M managed) neutralizes the price/openness pitch for webhooks | **Medium** | Compete only on "no second stateful service to operate" — Outpost is still a Go service needing Postgres + Redis + MQ |
| The fastapi-users successor expands into orgs/tenancy | **Medium** | Stay auth-agnostic; be the layer they integrate *with* |
| Postgres-only limits reach | **Low** | Correct trade for v1. Say so loudly in the README |
| `fastapi-tenancy` or `fastapi-rls` gains real traction first | **Low** | Both are solo, ≤4 stars, weeks old. Reassess quarterly; contributing may beat competing |

**Kill criteria — decide honestly, in advance:**

- Phase 0 ships with excellent docs and gets **fewer than 50 stars / zero inbound issues in 8 weeks** → the distribution problem is real and unsolved. Stop at the RLS layer, keep it as a personal tool.
- No **third-party production user** by the end of Phase 2 → stop before building the MCP pillar.
- FastMCP or the official SDK ships tenant-scoped identity forwarding → drop Phase 3 entirely, no regrets; it was always the thinnest.

---

## 9. Open decisions

1. **Licence** — MIT is the ecosystem norm and the least friction. Anything source-available kills library adoption (see Convoy, Hook0).
2. **Isolation modes at v1** — RLS only, or RLS + query-filter fallback? RLS-only is cleaner and more defensible; a filter mode widens the audience to non-Postgres users but doubles the correctness surface. *Recommendation: RLS-first, filter mode in v0.5 at the earliest.*
3. **Sync support** — async-only halves the test matrix and matches where FastAPI is going. *Recommendation: async-only for v1.*
4. **Is `emit()` a public API or an internal detail?** It is the single most distinctive thing in the library. *Recommendation: make it the headline.*
5. **Does core depend on SQLAlchemy at all?** Keeping it out means Mergen can serve Litestar and Django-Ninja later. *Recommendation: keep core storage-agnostic from day one — it costs almost nothing now and is expensive to retrofit.*

---

## Appendix — evidence base (all verified 2026-08-23)

**Tenancy:** django-tenants 1.9k★, v3.14.0 (2026-08-05, three releases that month) · fastapi-tenancy 4★ · sqlalchemy-tenants 4★ · tenantshield 1★ · fastapi-rls 0★ · tenant-schemas-celery 221★, v5.0.0 (2026-08-01) — the Django precedent proving tenancy+jobs demand · fastapi-users 6.2k★, v15.0.5 (2026-03-27), maintenance mode

**Jobs:** taskiq 2.2k★ v0.12.5 (2026-08-21), FastAPI `Depends()` verified working, no transactional enqueue · procrastinate 1.3k★ v3.9.0, external-connection deferral since 3.8.0 (2026-04-06), SQLAlchemy connector psycopg2-sync-only · pgqueuer 1.5k★ v1.3.2 (2026-07-27), no SQLAlchemy driver · arq 3.0k★ **maintenance-only** since Oct 2025 · fastapi-injectable 295★ v1.6.1 (2026-08-20) · best Python outbox library: 19★, dead since 2022

**Webhooks:** Svix MIT 3.2k★ — a Rust server you operate, OSS build self-admittedly behind hosted · Hookdeck Outpost Apache-2.0 985★, GA 2026-04-23 · standardwebhooks v1.1.0 (2026-07-21), sign/verify only · django-webhook 225★, stale since 2024-08-19 · no embeddable Python outbound library exists · asgi-idempotency-header dead 2022 · IETF idempotency draft expired 2025-10-15

**MCP:** spec revision 2026-07-28; `mcp` SDK 2.0.0; DCR deprecated in favour of CIMD; step-up auth standardized · FastMCP 27.3k★ v3.4.7 (2026-08-10), `from_fastapi()` + per-caller scope filtering both real · fastapi-mcp 11.9k★ but **last release 2025-07-28**, pinned to mcp 1.x · SEP-1880 (tool-level scopes) **closed, not planned**; SEP-1881 (scope-filtered discovery) draft, idle 9 months · `get_http_headers()` strips `authorization` → the confused-deputy default

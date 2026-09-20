# Threat model

## Scope and security objective

FastAPI Effects reduces cross-tenant, transactional-side-effect, delayed-authority, and
outbound-delivery failures caused by application bugs and process crashes. It is not a
sandbox against full compromise of the application process, database cluster,
migration credential, or host operating system.

## Protected assets

- tenant isolation and tenant-attributed history;
- application transaction integrity;
- event/delivery/attempt immutability and lineage;
- authorization provenance and revocation behavior;
- database credentials, user credentials, and webhook signing secrets;
- application business data inaccessible to the relay role;
- reliable delivery state and lease ownership;
- logs/metrics free of sensitive payload or secret material.

## Trust zones

| Zone | Trust | Responsibility |
|---|---|---|
| Principal provider | Trusted | Authenticate, select authorized tenant, reject disagreement |
| Application process | Trusted but fallible | Bugs expected; RLS/constraints contain classes of mistakes |
| Migration owner/PostgreSQL | Highly trusted | DDL, ownership, policies, durability |
| App DB credential | Trusted service credential | May bind tenant context; not end-user authentication |
| Relay process | Least-privileged trusted control plane | Cross-tenant only on FastAPI Effects schema |
| Handler app session | Trusted, tenant-bound | Fresh `fastapi_effects_app` transaction per attempt |
| Tenant payload and endpoint | Hostile | Validate content, size, identifiers, URL, network destination |
| Remote receiver | Hostile/fallible | May time out, lie, duplicate, or respond with oversized data |
| Observability backend | Lower trust | Receives approved identifiers and bounded metadata only |

## Attacker and failure capabilities

The model considers:

- a tenant sending malicious identifiers, payloads, URLs, redirects, or response data;
- application code issuing a query without a tenant filter;
- conflicting tenant sources at request entry;
- pooled connections retaining prior tenant context;
- role/table ownership, `BYPASSRLS`, superuser, grant, or search-path mistakes;
- a relay or handler process crashing at any state transition;
- a stale worker finishing after lease replacement;
- authority being revoked after emission;
- duplicate retries and abusive replay;
- DNS rebinding, special-use addresses, metadata endpoints, and TLS/authority confusion;
- secrets or payloads leaking through rows, logs, metrics, exceptions, or fixtures.

## Threat-to-control mapping

| Threat | Severity | Required controls | Diagnostic/conformance evidence | Residual risk |
|---|---:|---|---|---|
| Cross-tenant query mistake | High | Forced RLS, `USING` + `WITH CHECK`, tenant-safe FKs | `doctor` probes; `C-RLS-*`, `C-TENANT-FK` | Compromised app credential may deliberately bind another tenant |
| Pool tenant leakage | High | Transaction-local GUC, explicit UoW, cleanup in `finally` | commit/rollback/pool reuse probes | Driver/server defects outside supported matrix |
| Unsafe runtime role | High | Three roles; no owner/superuser/`BYPASSRLS` | catalog diagnostics and negative fixtures | Cluster admin can override controls |
| Relay reads business data | High | Schema-limited grants; separate handler session | live denial probes | Host/process compromise may steal another configured credential |
| Partial publication | High | One outer transaction; no sink during emit | atomicity and rollback suite | External application writes outside the UoW are not covered |
| Stale worker overwrite | High | Random lease token; compare-and-set renewal/finalization | stale finalize/renew chaos tests | Duplicate remote effect remains possible |
| Authority revocation ignored | High | Route mode; revalidate with origin ceiling | authority conformance suite | External resolver availability and correctness |
| Replay misuse | High | New linked delivery; reason/subject; terminal immutability | replay lineage tests and audit | Authorized operator can intentionally repeat an effect |
| Credential persistence | High | Allowlisted principal/snapshot schemas; redaction canaries | DB/log/metric/error scans | Application payload itself may contain secrets unless host validates DTO |
| Webhook SSRF | High | HTTPS-first, per-attempt DNS/IP validation, explicit-IP connect, no redirects | adversarial DNS/TLS/network fixtures | Proxy/egress configuration becomes a separate trust boundary |
| Response/payload resource abuse | Medium | byte/time/concurrency limits; no body persistence | size/timeout tests | Host resource exhaustion beyond configured process limits |
| Route mutation changes retry | Medium | immutable route/destination/policy snapshots | snapshot conformance tests | Unsupported snapshot version may dead-letter pending work |

## Accepted limitations

1. `set_config(..., true)` propagates trusted application context; it does not
   authenticate the holder of the app database credential.
2. FastAPI Effects cannot prevent a fully compromised application process from misusing any
   credential available to that process.
3. At-least-once delivery permits duplicates after ambiguous failure.
4. Remote receiver correctness and deduplication are outside the sender trust boundary.
5. Milestone 1 provides no production enforcement and must fail before pretending to
   do so.

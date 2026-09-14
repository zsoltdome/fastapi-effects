# FastAPI-Mergen

> **Status:** production-hardening alpha `0.11.0a1`; v1 external gates are open.

FastAPI-Mergen defines and tests the transaction boundary for **tenant-safe effects**
in async FastAPI and PostgreSQL systems.

> **One commit. Every effect keeps its tenant and authority provenance.**

Write application state and effect intent through the same SQLAlchemy transaction;
after commit, a fenced PostgreSQL relay executes immutable delivery snapshots through
fresh tenant-bound application sessions.

```python
async with uow:
    uow.session.add(invoice)
    await uow.emit(
        Event(type="invoice.created", version=1, data={"invoice_id": str(invoice.id)}),
        dedupe_namespace="invoice-create",
        dedupe_key=str(invoice.id),
    )
```

Delivery is at least once. Consumers that need one business result must deduplicate in
the same transaction as that result. Automatic retries retain the delivery/message ID;
manual replay creates a new linked delivery ID.

Start with the [installed-wheel PostgreSQL quickstart](docs/tutorials/quickstart.md).

## Capability status

| Capability | Status in `0.11.0a1` |
|---|---|
| Boundary Contract and conformance profiles | Implemented |
| Deterministic in-memory conformance driver | Reference-only |
| Real PostgreSQL transactional runtime | Implemented |
| Explicit SQLAlchemy UoW, dedupe, and immutable fan-out | Implemented |
| Leases, reconciliation, polling relay, and in-process handlers | Implemented |
| PostgreSQL roles, forced RLS, schema checks, and doctor | Implemented |
| Target-bound delegation and FastMCP 3.4 bridge | Implemented alpha |
| Encrypted, signed, SSRF-safe webhook delivery | Implemented beta |
| Durable Taskiq external executor | Implemented alpha |
| Transactional inbound command idempotency | Implemented alpha |
| API/schema compatibility, recovery, telemetry, and release evidence | Implemented locally |
| Two external deployments, independent review, RC observation | Required; not complete |

The source-recovery and milestone chronology is retained in
[`docs/planning/original-feasibility-plan.md`](docs/planning/original-feasibility-plan.md)
and the audit history; it is not release evidence for the current artifact.

## What this alpha provides

- Boundary Contract v1 with fourteen stable invariants;
- strict capability manifests and eight certification profiles;
- deterministic asynchronous conformance scenarios;
- an in-memory reference oracle with twenty injectable defects;
- JSON, JUnit, SARIF, and Markdown reports;
- independently verifiable manifest/report digests;
- credential-safe bounded evidence and deployment secret canaries;
- private, atomic report-file output;
- CLI, testing helpers, JSON schemas, CI workflow, and a cumulative milestone audit.
- atomic event and original-delivery persistence in a caller-owned async SQLAlchemy
  transaction;
- tenant-scoped dedupe with immutable payload conflict detection;
- PostgreSQL 16/18 RLS, role, migration, and pooled-context diagnostics;
- fenced delivery leases, deterministic retry, reconciliation, replay, and polling;
- snapshot, revalidated, and service-policy handler authority; and
- a real PostgreSQL adapter certifying the `core`, `delivery`, and `security` profiles.
- versioned exact-event webhook subscriptions and AES-GCM encrypted signing keys;
- Standard Webhooks-compatible deterministic bodies and rotation-overlap signatures;
- attempt-time DNS policy, explicit-IP TLS/HTTP, bounded response parsing, pause,
  replay, retention, and a real adapter certifying the `webhook` profile.
- durable per-attempt Taskiq handoffs, stable task IDs, duplicate worker fencing,
  principal restoration, expiry recovery, and a real `executor` profile adapter.
- transaction-owned command generations, exact request fingerprinting, bounded
  response replay, restricted retention, and a real `command` profile adapter.
- audience/method/path-bound delegation, scope/depth attenuation, key
  rotation/revocation, token-free audit, and a real `delegation` profile adapter.

This is an alpha integration release: polling remains the correctness path and
Taskiq is an optional transport for durable handler handoffs. Command idempotency
protects local database work and durable effect intent, not direct remote calls.
FastMCP tool visibility is not authorization; downstream routes verify delegation.
Webhook promotion to stable still requires recorded design-partner staging feedback.

## Run the reference suite

```bash
PYTHONPATH=src fastapi-mergen conformance run \
  --reference \
  --profile complete \
  --format json \
  --output build/conformance/report.json

PYTHONPATH=src fastapi-mergen conformance manifest \
  --reference > build/conformance/manifest.json

PYTHONPATH=src fastapi-mergen conformance verify \
  --manifest build/conformance/manifest.json \
  --report build/conformance/report.json
```

The first two commands normally run from an installed wheel or a `uv` environment, so
`PYTHONPATH=src` is not needed:

```bash
uv sync --group test
uv run fastapi-mergen conformance run --reference --profile complete
```

## Certify an implementation

```bash
fastapi-mergen conformance run \
  --adapter myapp.mergen_conformance:create_driver \
  --profile core \
  --format json \
  --output build/conformance/report.json
```

The adapter factory is trusted code imported with the authority of the CLI process.
Never accept its module path from a tenant or other untrusted caller.

## Guarantee language

FastAPI-Mergen does not promise generic exactly-once distributed execution.

- application state and original effect intent: **atomic local commit**;
- delivery or external execution: **at least once**;
- consumer-visible effectively-once behavior: requires durable consumer
  deduplication using the stable message identity;
- automatic retry: stable delivery/message identity and a new attempt identity;
- manual replay: a new linked delivery identity.

## Documentation

Start with:

1. [PostgreSQL quickstart](docs/tutorials/quickstart.md);
2. [Boundary Contract v1](docs/concepts/boundary-contract.md);
3. [Public API and compatibility](docs/reference/public-api.md);
4. [Production operations](docs/operations/migrations.md);
5. [Certification operations](docs/operations/certification.md);
6. [Security policy](SECURITY.md).
7. [Current remediation and open evidence gates](docs/planning/current-remediation.md).

## Development

```bash
uv sync --all-extras --all-groups
uv run python scripts/check.py
```

## Licence

MIT.

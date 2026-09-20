# FastAPI Effects

> **Durable, tenant-aware side effects for FastAPI and PostgreSQL.**

Many applications need to save information and then trigger another action, such as
sending a webhook, starting a job, or notifying another system. A crash at the wrong
moment can otherwise lose that action, repeat it unexpectedly, or run it under the wrong
customer account. FastAPI Effects records the intended action in the same PostgreSQL
transaction as the data change, then delivers it with retry and audit information intact.
It is useful when a multi-tenant FastAPI service needs stronger guarantees than a
best-effort background task.

[Documentation](https://github.com/zsoltdome/fastapi-effects/tree/main/docs) ·
[PyPI](https://pypi.org/project/fastapi-effects/) ·
[Changelog](https://github.com/zsoltdome/fastapi-effects/blob/main/CHANGELOG.md) ·
[Security](https://github.com/zsoltdome/fastapi-effects/blob/main/SECURITY.md) ·
[License](https://github.com/zsoltdome/fastapi-effects/blob/main/LICENSE)

> **Status:** production-hardening alpha `0.11.0a1`; v1 external gates are open.

Application changes and effect intent use the same SQLAlchemy transaction. After
commit, a fenced PostgreSQL relay executes immutable delivery snapshots through fresh,
tenant-bound application sessions.

## Install

FastAPI Effects supports Python 3.11 through 3.14.

```bash
python -m pip install fastapi-effects
```

Install only the integrations you use: `webhooks`, `otel`, `taskiq`, and `fastmcp`.
For example, `python -m pip install "fastapi-effects[webhooks]"` adds signed webhook
delivery without forcing that dependency set on every installation.

## Check the contract in 30 seconds

The bundled reference driver runs without PostgreSQL and demonstrates the core
atomicity, isolation, authority, retry, fan-out, lineage, and replay contracts:

```bash
fastapi-effects conformance run --reference --profile core --format markdown
```

The report ends with nine passing checks and includes this result:

```text
- Profile: `core`
- Contract: `1.0`
- Certified: **yes**
```

This certifies the reference driver, not an application deployment. Use a real adapter
and the PostgreSQL profiles to certify your integration.

## Commit state and effect intent together

The application owns the unit-of-work boundary:

```python
async with uow:
    uow.session.add(invoice)
    await uow.emit(
        Event(type="invoice.created", version=1, data={"invoice_id": str(invoice.id)}),
        dedupe_namespace="invoice-create",
        dedupe_key=str(invoice.id),
    )
```

If the transaction rolls back, neither the invoice nor its event and original
deliveries remain. If it commits, the relay can recover delivery after a crash without
reconstructing tenant, route, or authority state from mutable application data.

The
[installed-wheel PostgreSQL quickstart](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/tutorials/quickstart.md)
runs the complete application and relay path with separate administrator, migration,
application, and relay credentials.

## Why FastAPI Effects?

- Atomic local commit for business state, event, and original delivery rows.
- PostgreSQL roles and forced row-level security for tenant isolation.
- Fenced leases, immutable attempts, deterministic retry, and accountable replay.
- Snapshot, revalidated, and service-policy authority modes.
- Signed, encrypted, SSRF-resistant webhook delivery.
- Durable Taskiq handoff, inbound command idempotency, and scoped delegation.
- Executable conformance profiles with JSON, JUnit, SARIF, and Markdown evidence.

## Delivery guarantees

FastAPI Effects does not promise generic exactly-once distributed execution.

| Boundary | Guarantee |
|---|---|
| Application state and original effect intent | Atomic local commit |
| Delivery or external execution | At least once |
| Automatic retry | Stable delivery/message identity; new attempt identity |
| Manual replay | New delivery identity linked to the original |
| One consumer-visible business result | Consumer must deduplicate durably in its transaction |

## Capability maturity

| Capability | Status in `0.11.0a1` |
|---|---|
| Boundary Contract and conformance profiles | Implemented |
| Real PostgreSQL transactional runtime | Implemented |
| SQLAlchemy UoW, dedupe, immutable fan-out, relay, and replay | Implemented |
| PostgreSQL 16/18 roles, forced RLS, migrations, and diagnostics | Implemented |
| Target-bound delegation and FastMCP bridge | Alpha |
| Signed webhook delivery and receiver replay protection | Beta |
| Durable Taskiq external executor | Alpha |
| Transactional inbound command idempotency | Alpha |
| Compatibility, recovery, telemetry, and release evidence | Locally verified |
| Two external deployments, independent review, and RC observation | Required; open |

The in-memory driver is a reference oracle, not a production store. Detailed evidence
stages and remaining promotion gates are recorded in the
[current remediation record](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/planning/current-remediation.md).

## Requirements and compatibility

- Python 3.11–3.14 and async SQLAlchemy 2.x.
- PostgreSQL 16 and 18 are the certified runtime lines.
- FastAPI, SQLAlchemy, Pydantic, and Alembic are core dependencies.
- Webhooks, OpenTelemetry, Taskiq, and FastMCP are optional extras.
- Linux is the release-certification environment; the package is pure Python, but
  production behavior depends on PostgreSQL and integration services.
- Stable symbols and the deprecation policy are listed in the
  [public API inventory](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/reference/public-api.md).
- Python imports, the PostgreSQL schema and roles, telemetry names, protocol identifiers,
  environment variables, and the console command all use the `fastapi_effects` namespace
  (with `fastapi-effects` where packaging and command conventions require a hyphen).

## Limitations and non-goals

- The package is async-only and PostgreSQL-specific; it is not a synchronous or
  database-agnostic outbox.
- Polling is the correctness path. Taskiq is an optional durable transport for handler
  handoff, not the source of delivery truth.
- Command idempotency protects local database work and durable effect intent, not
  uncoordinated remote calls made inside an endpoint.
- FastMCP tool visibility is not authorization; downstream routes verify delegation.
- FastAPI Effects is not an authentication server, tenant manager, general queue,
  scheduler, or workflow engine.
- Webhook promotion to stable still requires recorded design-partner staging feedback.

Choose a simpler transactional outbox when tenant-bound authority, RLS enforcement,
replay accountability, and executable conformance evidence are not requirements.

## Documentation

- [PostgreSQL quickstart](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/tutorials/quickstart.md)
- [Boundary Contract](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/concepts/boundary-contract.md)
- [Architecture](https://github.com/zsoltdome/fastapi-effects/blob/main/ARCHITECTURE.md)
- [Runtime API](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/reference/runtime-api.md)
- [Webhook tutorial](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/tutorials/webhook-vertical-slice.md)
- [Operations guides](https://github.com/zsoltdome/fastapi-effects/tree/main/docs/operations)
- [Certification](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/operations/certification.md)
- [Known limitations](https://github.com/zsoltdome/fastapi-effects/blob/main/docs/planning/known-limitations.md)

## Development

```bash
uv sync --locked --all-extras --all-groups
uv run --locked --no-sync pre-commit install
uv run --locked --no-sync python scripts/check.py
```

See [CONTRIBUTING.md](https://github.com/zsoltdome/fastapi-effects/blob/main/CONTRIBUTING.md)
for branch, review, architecture, and security requirements.

## License

FastAPI Effects is authored by Zsolt Döme and distributed under the
[MIT License](https://github.com/zsoltdome/fastapi-effects/blob/main/LICENSE).

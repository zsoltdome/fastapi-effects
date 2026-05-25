# FastAPI-Mergen

> **Status:** pre-alpha specification and repository foundation (`0.0.1`).
> Milestone 1 intentionally contains no production persistence, RLS, relay, or
> webhook implementation.

FastAPI-Mergen is the planned transaction boundary for **tenant-safe effects** in
async FastAPI and PostgreSQL applications.

> **One commit. Every effect keeps its tenant and authority provenance.**

The product contract is deliberately narrower than a task queue or workflow engine:

- application state, an immutable event, and original delivery intents commit locally
  in one PostgreSQL transaction;
- delivery is **at least once**, not generically exactly once;
- automatic retries keep a stable delivery/message identity;
- an effectively-once consumer deduplicates that stable identity;
- manual replay creates a new delivery linked to immutable history;
- tenant and authorization provenance remain explicit across the boundary.

## What Milestone 1 provides

- a single `fastapi-mergen` distribution and `fastapi_mergen` import package;
- the normative Boundary Contract, security model, and five architecture decisions;
- a type-checked, fail-safe public API spike;
- a PostgreSQL 16/18 integration-test harness and role fixture design;
- clean-artifact, optional-extra, quality, and security CI gates;
- a bootable invoicing reference application whose effect operations remain explicit
  safety stubs until Milestone 2.

## Local setup

```bash
uv sync --all-extras --all-groups
uv run python scripts/check.py
```

Start one disposable integration database:

```bash
docker compose --profile pg16 up -d postgres16
uv run pytest -m integration
```

PostgreSQL 18 is available through profile `pg18`. Integration tests allocate unique
roles and databases and do not embed production-like credentials.

## API status

The public spike is importable and type-checkable. Entering `MergenUnitOfWork` or
calling `emit()` raises `MilestoneNotImplementedError` in `0.0.1`; this is deliberate.
The package does not pretend to enforce a security invariant before the Milestone 2
persistence, transaction, role, and RLS suites exist.

## Scope exclusions through the first differentiated product

FastAPI-Mergen does not provide authentication, tenant provisioning, a general task
queue, workflows, ordering, cancellation, inbound idempotency, MCP, synchronous
SQLAlchemy, non-PostgreSQL persistence, or an admin UI.

See [the documentation index](docs/index.md), [the Boundary Contract](docs/concepts/boundary-contract.md),
and [the Milestone 1 review](docs/milestone-1-review.md).

## Security

Read [SECURITY.md](SECURITY.md) and the [threat model](docs/concepts/threat-model.md)
before evaluating the design. PostgreSQL tenant settings are trusted context
propagation, not database-native authentication. Milestone 1 is not production code.

## Licence

MIT.

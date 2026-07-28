# FastAPI-Mergen

> **Status:** pre-alpha assurance release `0.6.0a1`.

FastAPI-Mergen defines and tests the transaction boundary for **tenant-safe effects**
in async FastAPI and PostgreSQL systems.

> **One commit. Every effect keeps its tenant and authority provenance.**

Milestone 7 delivers the executable **Mergen Boundary Contract Conformance and
Assurance Suite**. It certifies observable transaction, isolation, authority, retry,
replay, lease, context, idempotency, delegation, and evidence-minimization behavior
through a trusted application adapter.

## What this release provides

- Boundary Contract v1 with fourteen stable invariants;
- strict capability manifests and six certification profiles;
- deterministic asynchronous conformance scenarios;
- an in-memory reference oracle with twenty injectable defects;
- JSON, JUnit, SARIF, and Markdown reports;
- independently verifiable manifest/report digests;
- credential-safe bounded evidence and deployment secret canaries;
- private, atomic report-file output;
- CLI, testing helpers, JSON schemas, CI workflow, and a cumulative milestone audit.

This release does **not** turn the Milestone 1 API spike into a production event store.
The recoverable Git baseline is the verified Milestone 1 repository; later runtime
source archives were unavailable in this environment. The conformance package is
therefore intentionally implementation independent: production PostgreSQL, queue,
webhook, idempotency, and delegation implementations are certified through adapters
that call their real paths.

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

1. [Boundary Contract v1](docs/concepts/boundary-contract.md);
2. [Conformance architecture](docs/concepts/conformance.md);
3. [Certification operations](docs/operations/certification.md);
4. [Conformance API reference](docs/reference/conformance-api.md);
5. [Security policy](SECURITY.md).

## Development

```bash
uv sync --all-extras --all-groups
uv run pytest -q tests/conformance tests/security tests/unit
uv run python scripts/audit_milestone_seven.py --skip-git-governance
```

## Licence

MIT.

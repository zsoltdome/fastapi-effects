# Compatibility and executed evidence

The candidate support envelope is Python 3.11–3.14, PostgreSQL 16 and 18, FastAPI
0.141.x, Pydantic 2.x, SQLAlchemy 2.0.x, Alembic 1.x, and `asyncpg` 0.31.x. The lock
file records the latest resolved set; the compatibility workflow separately resolves
minimum direct versions.

| Evidence ID | Environment | Coverage |
| --- | --- | --- |
| `compat-python-${python}` | Python 3.11, 3.12, 3.13, 3.14 | unit, security, conformance, imports, packaging metadata |
| `compat-pg16-py311` | PostgreSQL 16 / Python 3.11 | migrations and all real integration profiles |
| `compat-pg18-py314` | PostgreSQL 18 / Python 3.14 | migrations and all real integration profiles |
| `compat-min-base` | Python 3.11 / lowest direct base dependencies | type, unit, security, conformance |
| `compat-min-${extra}` | lowest direct `webhooks`, `otel`, `taskiq`, `fastmcp` extra | import and owned tests |
| `compat-latest-all` | current lock / every extra | complete non-integration suite and artifact smoke |

Workflow job names are machine-readable evidence identifiers and appear in GitHub check
runs. A passing table entry means the matching job ran; this document does not convert
an intended version range into executed evidence.

The repository retains a [historical local compatibility snapshot](evidence/compatibility-local.json)
that is commit/lock bound and explicitly has no release authority. Each hosted matrix job
publishes its own execution-bound JSON artifact containing the package version, commit, lock
digest, runtime, installed distributions, workflow run identity, and database/driver versions
when applicable.

The certified PostgreSQL DBAPI is `asyncpg`. Async psycopg is deferred because the
runtime depends on asyncpg-specific operational testing and one driver is sufficient for
v1. Adding psycopg would multiply cancellation, pooling, server-side binding, and
failover combinations without current design-partner evidence.

Optional extras are isolated: importing `fastapi_effects` and PostgreSQL persistence does
not import webhook crypto/networking, OpenTelemetry SDK, Taskiq, or FastMCP. Missing
optional dependencies fail at the feature boundary with
`fastapi_effects.optional_dependency` and an installation instruction.

The distribution and command are named `fastapi-effects`. Python imports, the
PostgreSQL schema and roles, telemetry names, environment variables, protocol
identifiers, and error codes use `fastapi_effects`. The pre-release namespace was
removed before v1; this alpha does not provide compatibility aliases or an automatic
database-object migration from earlier development snapshots.

See [Public API](reference/public-api.md) for compatibility semantics and
[Migrations](operations/migrations.md) for the independent database revision contract.

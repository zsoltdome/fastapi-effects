# Contributing

FastAPI Effects treats documentation, database constraints, migrations, and failure
tests as part of implementation—not release cleanup.

## Development

```bash
uv sync --locked --all-extras --all-groups
uv run --locked --no-sync pre-commit install
uv run --locked --no-sync python scripts/check.py
```

The complete command performs formatting verification, linting, strict typing, tests,
documentation validation, package build, artifact inspection, and repository-contract
validation. Use `uv run --locked --no-sync pytest <path>` for a focused test while
iterating, then run the complete command before requesting review.

Pre-commit delegates to the same locked Ruff, mypy, and documentation tools used by the
full gate. It does not maintain a second set of tool versions.

## Branches and commits

- Branch from `main`.
- Use a short typed branch name with three to seven words, for example
  `feat/add-public-api-spike`.
- Use imperative commit subjects of three to seven words, for example
  `Add provisional public API`.
- Keep one coherent change per commit.
- Do not bypass tests for security-sensitive code.
- Preserve the real author and committer recorded by the contributor, bot, or merge
  workflow. Never rewrite an external contribution to impersonate the institute.

The recovery-baseline provenance check is an archival maintainer audit, not a
contributor requirement. Normal development and CI invoke the structural gate with
`--skip-git-governance`. Source archives without `.git` can run all code, test,
documentation, and artifact checks; they cannot establish Git-history provenance and
must not claim to do so.

## Architecture changes

Any change to atomicity, identity, dedupe, replay, RLS trust, authorization, routing,
lease behavior, or supported scope requires an ADR before implementation. Update the
Boundary Contract and conformance mapping in the same pull request.

Start with [ARCHITECTURE.md](ARCHITECTURE.md) for the component map and
[`docs/reference/public-api.md`](docs/reference/public-api.md) for compatibility scope.

## Pull request definition of done

- tests include positive and negative cases;
- public API and operational behavior are documented;
- no secret, credential, payload, or response body is logged by default;
- no handler/network I/O occurs while database claim locks are held;
- built wheel and source checkout behave equivalently;
- no queue, MCP, workflow, ordering, cancellation, or inbound-idempotency feature is
  introduced before its gated milestone.

Maintainers review correctness, tests, compatibility, security boundaries, and public
documentation. Small changes may use one maintainer review; release, migration,
authorization, tenant-isolation, or cryptographic changes require a second maintainer.

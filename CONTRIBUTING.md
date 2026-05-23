# Contributing

FastAPI-Mergen treats documentation, database constraints, migrations, and failure
tests as part of implementation—not release cleanup.

## Development

```bash
uv sync --all-extras --all-groups
uv run python scripts/check.py
```

The complete command performs formatting verification, linting, strict typing, tests,
package build, artifact inspection, and repository-contract validation.

## Branches and commits

- Branch from `main`.
- Use a short typed branch name with three to seven words, for example
  `feat/add-public-api-spike`.
- Use imperative commit subjects of three to seven words, for example
  `Add provisional public API`.
- Keep one coherent change per commit.
- Do not bypass tests for security-sensitive code.
- This implementation history uses only `mergen-institute` as author and committer.

## Architecture changes

Any change to atomicity, identity, dedupe, replay, RLS trust, authorization, routing,
lease behavior, or supported scope requires an ADR before implementation. Update the
Boundary Contract and conformance mapping in the same pull request.

## Pull request definition of done

- tests include positive and negative cases;
- public API and operational behavior are documented;
- no secret, credential, payload, or response body is logged by default;
- no handler/network I/O occurs while database claim locks are held;
- built wheel and source checkout behave equivalently;
- no queue, MCP, workflow, ordering, cancellation, or inbound-idempotency feature is
  introduced before its gated milestone.

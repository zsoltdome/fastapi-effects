# Agent instructions

These instructions apply to the whole repository. Human maintainers own every merged
change and its security, compatibility, and operational consequences.

## Canonical environment and checks

- Install with `uv sync --locked --all-extras --all-groups`.
- Run the full gate with `uv run --locked --no-sync python scripts/check.py`.
- Run focused tests before the full gate when iterating.
- Use `uv lock --check` after dependency edits and commit `uv.lock` with
  `pyproject.toml`.
- Pre-commit hooks use the same locked Ruff, mypy, and documentation commands.

## Architecture rules

- Preserve caller-owned unit-of-work transaction boundaries.
- Never perform handler, broker, or network I/O while database claim locks are held.
- Restore tenant and authority context in fresh sessions for delivery work.
- Keep credentials, plaintext webhook secrets, Python callables, and transport clients
  out of persisted route snapshots.
- Treat PostgreSQL roles, forced RLS, fenced leases, stable delivery identities, and
  immutable attempt history as security boundaries.
- Do not claim generic exactly-once execution. Automatic retry retains the delivery
  identity; manual replay creates a linked identity.
- Record changes to atomicity, identity, replay, RLS, authorization, routing, leases,
  or supported scope in an ADR and the Boundary Contract mapping.

Read `ARCHITECTURE.md` for the component map and `docs/reference/public-api.md` before
changing exports. Names not documented there are internal even when importable.

## Tests and documentation

- Add positive and negative tests for behavior changes and a regression test for every
  reproducible bug fix.
- Mark PostgreSQL-dependent tests with `integration`; keep packaging, conformance,
  security, and chaos classifications accurate.
- Keep examples deterministic and safe by default.
- Update public and operational documentation with behavior changes.
- Executable Markdown fences are registered in
  `docs/planning/documentation-scenario-inventory.json`; update their hashes and
  evidence when a block changes.

## Generated and sensitive files

- Do not edit build outputs, distributions, coverage files, caches, generated evidence,
  or local benchmark output as source.
- Do not commit `.env` files, DSNs, tokens, credentials, payloads, response bodies,
  private keys, or plaintext webhook secrets.
- Preserve bounded, credential-safe logs and evidence.
- Treat release artifacts as immutable; publishing must promote the exact artifact that
  passed release verification.

## Definition of done

A change is complete when formatting, linting, strict typing, relevant focused tests,
documentation checks, package checks, and the full local gate pass in proportion to
the change. Report any hosted, database, or external evidence that could not be run.

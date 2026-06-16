# FastAPI-Mergen Milestone 1 implementation report

**Date:** 2026-08-24  
**Version:** `0.0.1`  
**Owner:** `mergen-institute`  
**Scope:** specification and repository foundation

## Implemented

Milestone 1 is represented as executable repository work rather than documentation-only
intent. The repository contains:

- one `fastapi-mergen` distribution with the `fastapi_mergen` import root and
  `fastapi-mergen` console command;
- a deliberately narrow root API and documented `postgres` and `sqlalchemy` integration
  namespaces;
- immutable principal, event, retry-policy, route, and effect-context API-spike values;
- fail-closed stubs for every security or durability behavior deferred to Milestone 2;
- Boundary Contract v0.1, guarantee vocabulary, threat model, authorization rules, and five
  accepted ADRs;
- a disposable PostgreSQL 16/18 integration harness with owner, app, relay, and deliberately
  unsafe role variants;
- quality, package, security, and release workflows with third-party actions pinned to
  immutable revisions;
- clean artifact probes for the base wheel/source package and both wheel extras;
- an invoicing reference application that boots and renders OpenAPI without claiming that
  persistence exists;
- structural and architecture gates that enforce scope, public exports, documentation
  vocabulary, repository governance, and the M2/M3 effort totals.

## Double-check findings incorporated

The final audit corrected several API-spike details before sign-off:

1. `revalidate` routes cannot freeze without an authorization resolver.
2. named service-policy capabilities are resolved synchronously at startup and pinned into
   route snapshots before the registry freezes.
3. service-capability updates are staged and committed atomically to avoid partially
   mutated route state after a validation failure.
4. route keys cannot change event type; only the highest registered route version is active
   for new emissions.
5. optional dependency failures remain actionable for dotted imports.
6. error summaries and dedupe keys reject control characters and avoid exposing payload or
   secret content through default exception strings.
7. clean-wheel probes remove inherited checkout paths so imports must come from the
   installed artifact.
8. the documented `fastapi_mergen.postgres.PostgresStore` and
   `fastapi_mergen.sqlalchemy.MergenUnitOfWork` namespaces are importable and tested.

## Local validation

The final repository is validated with:

```text
python -m compileall -q src examples scripts tests
python -m pytest -q -m "not integration"
python scripts/architecture_gate.py
python scripts/verify_milestone_one.py
python scripts/build_and_test_artifacts.py --offline-system-packages
```

The exact final counts and results are recorded in `docs/milestone-1-review.md` after the
clean release-candidate run.

## Environment-limited checks

The implementation is honest about checks that could not be executed in the provided
container:

- no Docker daemon or PostgreSQL 16/18 server was available, so live integration tests are
  present but skipped locally;
- Ruff and mypy were not installed and the container had no outbound package-index access,
  so their committed configurations are enforced by CI rather than reported as locally
  passing;
- a resolver-generated `uv.lock` was not fabricated offline. The first connected dependency
  change must run `uv lock`, review the diff, and commit it before a public alpha tag.

## Git governance

The ZIP preserves `.git`, `main`, and the typed feature branches used for the milestone.
The verifier enforces:

- branch slugs with three to seven short words;
- commit subjects with three to seven words;
- `mergen-institute <mergen-institute@users.noreply.github.com>` as the sole author and
  committer identity across all local branches;
- a clean working tree at final packaging time.

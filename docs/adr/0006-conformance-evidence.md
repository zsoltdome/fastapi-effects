# ADR 0006 — Versioned executable conformance evidence

**Status:** Accepted
**Date:** 2026-08-26

## Context

The Mergen thesis depends on cross-boundary invariants that ordinary library API tests
cannot establish for custom adapters or deployments. A prose contract without
executable evidence is easy to reinterpret, while a runtime-specific suite would lock
the project to one queue, database wrapper, webhook transport, or MCP integration.

Evidence files may contain tenant identifiers, operational metadata, or exception
content. They therefore need a stable schema, data minimization, and independent
verification.

## Decision

1. Publish Boundary Contract v1 as transport-neutral facet protocols and deterministic
   scenarios.
2. Require a strict, canonical capability manifest identified by SHA-256.
3. Bind each report to the exact manifest digest and selected certification profile.
4. Certify only when every required invariant has passing evidence and no check is
   failed, skipped, or errored.
5. Provide JSON as the archival format and JUnit, SARIF, and Markdown projections.
6. Reject duplicate JSON keys and re-compute status, counts, certification, and digest
   when archived evidence is parsed.
7. Never include exception messages or raw credentials in public evidence.
8. Support deployment-provided secret canaries through environment-variable names,
   not command-line literal values.
9. Treat adapter factories as trusted code; never import tenant-controlled modules.
10. Maintain a deterministic reference driver with injected faults so the suite proves
    it can detect violations rather than only produce green output.

## Consequences

- Adapter authors can certify one common contract without adopting Mergen's internal
  storage implementation.
- A certification claim is specific to the adapter, manifest, implementation version,
  profile, and run evidence.
- The suite remains empirical rather than formal verification.
- Adding or changing an invariant becomes a compatibility event requiring schema,
  scenario, fault, documentation, and release updates.
- The conformance specification becomes a stronger product asset than adding another
  executor or transport integration.

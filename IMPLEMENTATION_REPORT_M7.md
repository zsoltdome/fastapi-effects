# FastAPI-Mergen Milestone 7 implementation report

**Version:** `0.6.0a1`
**Milestone:** Boundary Contract Conformance and Assurance Suite
**Date:** 2026-08-26

## Scope decision

The audited roadmap explicitly ended at Milestone 6. Milestone 7 is defined here as
the next planned product asset: the implementation-independent Boundary Contract and
Assurance Suite. It does not add another queue, workflow engine, storage backend, or
MCP server.

## Implemented capabilities

- Boundary Contract v1 descriptor with twelve stable invariants;
- strict capability manifests with prerequisite validation and canonical SHA-256
  identity;
- `core`, `delivery`, `security`, and `complete` certification profiles;
- runtime-checkable facet protocols for transaction, delivery, authority, context,
  command idempotency, and delegation boundaries;
- sixteen deterministic scenarios;
- bounded per-check timeouts, fail-fast option, cleanup checks, and fail-closed status;
- deterministic in-memory reference driver;
- fourteen injected faults proving that the suite detects broken implementations;
- secret-key redaction and optional deployment-provided secret canaries;
- JSON, JUnit, SARIF, and Markdown reporters;
- strict archived-report parsing and independent manifest/report verification;
- private-by-default atomic output files with symlink refusal;
- CLI commands for running, inspecting manifests, printing the spec, and verifying
  archived evidence;
- reusable `assert_certified` test helper;
- JSON schemas, documentation, ADR, CI workflow, and a cumulative release audit.

## Certification semantics

A report is certified only when:

1. its profile is supported;
2. every profile invariant has passing evidence;
3. no selected check failed, skipped, or errored;
4. the report's derived status, counts, and digest are internally consistent;
5. archived verification binds the report to the exact capability-manifest digest.

## Security decisions

- exception messages never enter reports;
- evidence is recursively bounded and sensitive field names are redacted;
- manifest metadata containing sensitive field names is rejected;
- secret canaries are read indirectly from environment variables;
- report output files use mode `0600`, atomic replacement, and symbolic-link refusal;
- dynamic adapter loading is explicitly trusted code execution;
- JSON parsers reject duplicate keys and malformed UTF-8;
- an adapter cannot certify a profile merely by setting the serialized `certified`
  field.

## Verification boundary

The reference harness proves the assurance system itself behaves as designed. It is
not a production database, queue, webhook transport, or delegation issuer. A custom
adapter must connect the protocol methods to the actual implementation path being
certified.

Live PostgreSQL, queue broker, network, or FastMCP tests remain the responsibility of
the corresponding adapter and deployment CI. An unavailable environment-dependent
check must be represented as not run or unsupported, never as a pass.

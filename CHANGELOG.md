# Changelog

All notable changes are documented here. The project follows Semantic Versioning,
with explicit pre-1.0 contract and evidence-schema notes.

## 0.6.0a1 - 2026-08-26

### Added

- Boundary Contract v1 executable conformance package.
- Strict capability manifests and `core`, `delivery`, `security`, `webhook`,
  `executor`, and `complete` profiles.
- Nineteen deterministic scenarios and twenty injected reference faults.
- JSON, JUnit, SARIF, and Markdown evidence reporters.
- Strict report parsing, report digests, and manifest-bound archived verification.
- Deployment secret-canary checks and private atomic report output.
- Conformance CLI, reference driver, testing assertion helper, JSON schemas, CI, ADR,
  operator documentation, and Milestone 7 audit.

### Changed

- Package version advanced from the Milestone 1 foundation to the independent
  assurance release.
- Boundary Contract documentation expanded from seven MDP invariants to fourteen
  cross-milestone invariants.

### Security

- Public evidence omits exception messages and recursively redacts sensitive fields.
- Manifest metadata rejects sensitive field names.
- Report output refuses symbolic links and defaults to mode `0600`.

## 0.0.1 - 2026-08-24

### Added

- Milestone 1 repository and packaging foundation.
- Boundary Contract v0.1, threat model, and architecture decision records.
- Provisional public API that fails safely before Milestone 2 behavior.
- PostgreSQL integration harness and clean-artifact CI design.
- Invoicing reference application skeleton.

# Conformance API reference

Import assurance symbols from `fastapi_mergen.conformance`, not the package root.
This keeps the runtime public surface narrow.

## Contract values

### `Capability`

Declares implementation facets such as transactional effects, tenant isolation,
authorization, delivery leases, command idempotency, and delegation.

### `Invariant`

Stable identifiers `BC-01` through `BC-14`.

### `CertificationProfile`

`core`, `delivery`, `security`, `webhook`, `executor`, or `complete`.

### `CapabilityManifest`

An immutable strict declaration. Important methods and properties:

```python
manifest.as_dict()
manifest.canonical_bytes()
manifest.digest
manifest.to_json()
CapabilityManifest.from_dict(...)
CapabilityManifest.from_json(...)
```

## Execution

### `RunnerConfiguration`

```python
RunnerConfiguration(
    profile=CertificationProfile.CORE,
    check_timeout_seconds=None,
    fail_fast=False,
    secret_canaries=(),
)
```

### `ConformanceRunner`

```python
report = await ConformanceRunner(configuration).run(driver)
```

The driver is closed at the end of the run. A new driver instance is recommended for
an independent subsequent run.

## Evidence

### `CheckResult`

Contains check ID, invariant, status, severity, bounded summary, duration, normalized
evidence, remediation, and optional exception type.

### `ConformanceReport`

Contains profile, exact manifest digest, check results, timestamps, run ID, environment,
contract version, and schema version.

```python
report.status
report.certified
report.counts()
report.as_dict()
report.canonical_bytes()
report.digest
ConformanceReport.from_json(...)
```

Parsing re-computes every derived field and rejects inconsistent evidence.

### `decide(report)`

Returns a `CertificationDecision` with missing invariants and failed, errored, or
skipped check IDs.

### `verify_evidence(report, manifest)`

Binds a parsed report to the exact manifest and returns the certification decision.
A digest or profile-declaration mismatch raises `MergenConfigurationError`.

### Reporters

```python
render_report(report, ReportFormat.JSON)
render_report(report, ReportFormat.JUNIT)
render_report(report, ReportFormat.SARIF)
render_report(report, ReportFormat.MARKDOWN)
write_report(path, content)
```

## Testing helpers

```python
from fastapi_mergen.testing import (
    Fault,
    ReferenceBoundaryDriver,
    assert_certified,
)
```

`ReferenceBoundaryDriver` is an in-memory specification oracle. `Fault` injects one
observable contract violation. `assert_certified` raises a bounded assertion listing
only missing invariant and non-passing check IDs.

## Facet protocols

Adapter authors implement `BoundaryDriver` and the protocols required by the manifest:

- `TransactionalEffectsFacet`;
- `DeliveryLeaseFacet`;
- `AuthorizationFacet`;
- `ContextLifecycleFacet`;
- `CommandIdempotencyFacet`;
- `DelegationFacet`;
- `WebhookFacet`;
- `ExternalExecutorFacet`.

A manifest that declares an invariant without all prerequisite capabilities is
rejected before execution.

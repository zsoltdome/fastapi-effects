# Boundary Contract conformance map

| Contract | Planned suite |
|---|---|
| BC-01 Atomic intent | `tests/conformance/test_atomicity.py` |
| BC-02 Tenant continuity | `tests/conformance/test_isolation.py`, `test_context_lifecycle.py` |
| BC-03 Authority provenance | `tests/conformance/test_authority.py` |
| BC-04 Stable retry identity | `tests/conformance/test_delivery.py` and crash matrix |
| BC-05 Independent fan-out | `tests/conformance/test_delivery.py` |
| BC-06 Causal lineage | delivery and observability conformance suites |
| BC-07 Replay accountability | delivery/replay conformance suites |

Milestone 1 validates the map and terminology. Milestone 2/3 must provide positive and
negative executable cases before claiming the corresponding runtime guarantee.

## Quarter release-scope mapping

[ADR-017](../adr/ADR-017-quarter-release-scope.md) changes maturity classification,
not the Boundary Contract. BC-01 through BC-07 remain required for the PostgreSQL and
signed-webhook stable target. Taskiq, command idempotency, delegation, and FastMCP
helpers remain provisional, but every Boundary Contract rule they exercise and their
shipped security/recovery regressions remain mandatory. Internal implementation status
cannot be used to bypass a conformance rule.

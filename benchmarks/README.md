# Reproducible runtime benchmark

Run `python scripts/benchmark.py --admin-dsn "$FASTAPI_EFFECTS_TEST_ADMIN_DSN" --output result.json`.
The harness creates and destroys a unique database and restricted roles. It records the
host/Python/PostgreSQL/package versions, dataset shape, single- and multi-tenant emission,
claim throughput, tenant fairness, backlog age, retry scheduling, signed in-process
webhook transport and a deduplicating receiver,
same-key command contention, and command pruning/index size.

Results are engineering evidence, not cross-host marketing comparisons. The quick CI
workload detects correctness and gross regressions; it emits performance warnings without
failing correctness. A release record must retain the JSON from PostgreSQL 16 and 18 and
describe CPU, memory, storage, virtualization, thermal policy, and concurrent load.

`thresholds.json` contains deliberately loose shared-runner alert thresholds. Crossing
one adds `performance_alerts` but does not change the exit status; correctness invariants
remain independently fatal.

`results/local-pg16.json` and `results/local-pg18.json` are retained quick-run examples
from the same host. Their tiny nine-delivery dataset proves harness behavior and provides
no production capacity claim; release capacity evidence must use the documented workload.

# Performance and capacity planning

Capacity decisions must use `scripts/benchmark.py` against the intended PostgreSQL
topology. The harness separates correctness invariants (all tenants observed, bounded
per-tenant claim run, one command execution) from measurements. Correctness failures
fail CI; latency and throughput are advisory because shared CI runners are noisy.

Start with relay `batch_size=50` and `per_tenant=5`, measure oldest backlog age rather
than row count alone, and scale workers only while lease-expiry and database-lock rates
remain flat. A lease must exceed the handler timeout. Command contention intentionally
serializes one identity and should be load-tested with the application's actual hot-key
distribution.

PostgreSQL does not immediately return table files to the operating system after row
pruning. Observe live/dead tuple counts, index bytes, autovacuum, and transaction age.
Retention should use small bounded batches and pause when foreground latency rises.

The repository contains no universal SLA or throughput claim. Promote a result only when
its JSON evidence contains hardware, runtime/database versions, dataset shape, and both
single- and multi-tenant workloads.

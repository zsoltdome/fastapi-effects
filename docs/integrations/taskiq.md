# Taskiq integration

Install `fastapi-effects[taskiq]`, migrate through `0003_taskiq`, and choose a Taskiq
broker supported by your deployment. FastAPI Effects does not replace Taskiq: Taskiq moves
one small handoff message to a worker, while FastAPI Effects remains authoritative for
attempt state, leases, retries, dead letters, and principal provenance.

```python
worker = TaskiqWorkerBridge(
    sessions=relay_sessions,
    executor=fastapi_effects.handler_executor(),
)
bridge_task = register_taskiq_bridge(broker, worker)
taskiq_sink = TaskiqDeliverySink(
    sessions=relay_sessions,
    task=bridge_task,
)
```

Run the broker's normal Taskiq worker command against the module that constructs
and exports `broker`. Register exactly one bridge task in every sender and worker
process. Use the same frozen FastAPI Effects route registry and tenant application-session
factory in workers.

Do not install Taskiq retry middleware on this task. FastAPI Effects snapshots retry policy
on the delivery and creates the next attempt after a fenced failure. Broker
redelivery is duplicate transport, not an application retry, and produces a bounded
no-op once the handoff is already executing or terminal. Before admitting a handler,
the worker locks and verifies the handoff, referenced attempt, and parent delivery as
one coherent state: the parent must still be leased, its current token must belong to
that still-started attempt, and the aggregate attempt deadline must remain open. A
delayed handoff from a reclaimed attempt is terminalized without opening an application
session or invoking the handler.

Broker enqueue shares the parent attempt deadline. A timeout is treated as ambiguous
acceptance: the durable prepared handoff and stable task ID allow either the delivered
worker or bounded recovery to win without treating broker acknowledgement as delivery
success.

Deploy recovery beside the polling relay and call `TaskiqRecovery.run_once()` on a
bounded interval. Graceful shutdown stops new polling, waits for current broker
enqueue calls, and lets workers finish within their execution/lease deadline.
Unclean shutdown is safe but may repeat handler effects; deduplicate them with the
stable delivery identity.

Certified range: Taskiq `>=0.12.5,<0.13`, Taskiq Redis `>=1.2,<2`, Python 3.11–3.14,
PostgreSQL 16–18, and the `asyncpg` driver. The cumulative profile uses Redis Streams
and a separate Taskiq CLI worker process to prove serialization and worker lifecycle.
Other broker plugins retain their own compatibility and durability requirements and
must be certified by the host application.

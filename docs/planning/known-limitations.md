# Known limitations

- External delivery is at least once; a durable consumer dedupe transaction is required
  for one effective result.
- PostgreSQL 16/18 with asyncpg is the only certified persistence path. Async psycopg,
  synchronous APIs, other databases, and workflow orchestration are excluded.
- Polling is the correctness path. Taskiq transports durable handoffs but does not own
  retry policy or make broker acceptance terminal.
- Webhook networking supports reviewed HTTP/1.1 behavior and strict public-address TLS;
  proxy meshes and custom DNS policies need environment validation.
- The reference delegation key ring is in memory. Production deployments need a reviewed
  key provider and availability/rotation runbook.
- Feature implementation modules remain provisional as listed in the public API inventory.
- Taskiq handoff retention is intentionally not automated in v1.
- No external design-partner deployment, independent security review, RC observation, or
  trusted publication has been recorded. Every supported `1.x` or later RC and final
  version is evaluated semantically and fails closed when its bound evidence is absent.

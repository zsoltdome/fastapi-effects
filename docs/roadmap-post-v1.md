# Bounded post-v1 roadmap

Rank work only from production demand and retained evidence:

1. v1 correctness/security defects and migration/operator friction;
2. performance and observability improvements backed by candidate measurements;
3. promotion of provisional Python integration surfaces after usage evidence;
4. Taskiq handoff retention if operational volume justifies a safe dependency policy;
5. async psycopg certification if a partner requires it.

Do not add workflow orchestration, non-PostgreSQL storage, synchronous support, or new
broker/webhook/MCP adapters without multiple concrete deployments and an owned test,
migration, security, documentation, and support plan.

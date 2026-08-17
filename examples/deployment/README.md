# Deployment reference

This reference starts PostgreSQL only; application, migration, and relay processes are
deliberately separate so their credentials cannot be accidentally shared in one image.

1. Copy `.env.example` to an untracked secret source and replace every placeholder.
2. Start `docker compose up -d postgres` and wait for health.
3. As the migration owner, run Alembic to head and `fastapi-mergen schema check`.
4. Start the FastAPI app with only `mergen_app` credentials.
5. Start the polling relay with only `mergen_relay` credentials.
6. Run doctor separately against app and relay credentials, then applicable conformance.

Pin the PostgreSQL image by digest in production, place it on a private network, use TLS
for non-loopback connections, source credentials from a secret manager, set CPU/memory
and connection limits, and configure tested backup/PITR before traffic. The compose file
is a topology teaching aid, not a high-availability database design.

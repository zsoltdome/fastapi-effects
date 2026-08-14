# Failure and recovery model

FastAPI-Mergen promises durable committed intent and fenced stale work. Delivery is at
least once. It does not promise exactly-once external effects. A consumer achieves one
effective result only by durably deduplicating the stable delivery, webhook, task, or
command identity.

`scripts/chaos_harness.py` executes the reviewed scenario manifest. The PostgreSQL
profile covers rollback before commit, effect-publication failure, remote webhook success
before local finalization, broker duplicates, expired worker execution, key-provider
outage, and revoked keys. The same nodes run on PostgreSQL 16 and 18 in compatibility CI.

Real connection termination is exercised inside an application transaction on PostgreSQL
16 and 18. The operator-controlled `scripts/rehearse_postgres_restart.py` rehearsal also
restarts each disposable database container and proves that a committed event/delivery
identity, schema compatibility, doctor checks, and pool reconnection survive. Its bounded
reports are `docs/evidence/postgres-restart-16.json` and
`docs/evidence/postgres-restart-18.json`.

Managed-service failover remains `external` because the supported local single-node
environment has no promotion target. Run it in staging and terminate the application
connection at each transaction boundary:

- before commit: retry the command; no event or business write may exist;
- after an ambiguous commit response: retry with the same command/dedupe identity;
- after claim: wait past lease expiry, reconcile, and reject the stale lease token;
- after receiver/broker acceptance: retry with the same delivery/task identity;
- after remote success and before finalization: expect a duplicate attempt and rely on a
  cooperating deduplicating consumer;
- during replay or pruning: rerun the bounded operation and retain immutable lineage.

Key-provider unavailability stops issuance and denies unverifiable credentials. It is
retryable only before downstream acceptance. Explicit revocation is terminal and must not
fall back to an older or unknown key.

After any failure, run schema check and doctor, compare backlog age/dead/lease metrics,
run applicable real conformance profiles, and record ambiguous identities before manual
replay. Never bulk replay solely from an HTTP timeout.

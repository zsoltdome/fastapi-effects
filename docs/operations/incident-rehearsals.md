# Incident rehearsal record

The local hardening run on 2026-08-30 rehearsed these bounded scenarios through tests:

| Scenario | Evidence | Expected decision |
| --- | --- | --- |
| Key compromise/revocation | delegation and webhook key tests | revoke immediately, deny old credential, rotate controlled key, inspect token-free audit |
| Secret rotation overlap | webhook/delegation rotation tests | bounded overlap only; never silently extend eligibility |
| Dead-letter/lease surge | lease retry/reconcile and chaos tests | stop replay, stabilize dependency, reconcile fenced work, page on age/dead rate |
| Replay misuse | immutable replay lineage/security tests | require operator authority and reason; new linked identity only |
| Failed migration/downgrade | all-revision matrix and nonempty guard | stop writers, preserve backup, forward-fix or restore separately |
| Logical restore | PostgreSQL 16/18 data-only rehearsal | compare protected identities, schema check, doctor/conformance before traffic |
| Database connection loss/restart | PostgreSQL 16/18 transaction termination and disposable-container restart | roll back uncommitted work, preserve committed identity, reconnect with no context leak, rerun doctor |
| Webhook signing-key lifecycle | two-tenant revoked and expired-retiring keys, wrong-tenant lookup, killed terminal finalization | disclose no cross-tenant material, preserve immutable snapshot/attempt identity, reconcile and finish terminal accounting without blocking the sibling tenant |
| Relay database control boundaries | live backend termination during reconciliation, claim, tenant-bound application-session setup, and success/failure finalization | keep programming errors visible, reconnect after classified transport loss, fence stale attempts, and preserve sibling progress |
| PostgreSQL commit acknowledgement loss | protocol-aware proxy drops the server's `ReadyForQuery` only after application, claim, or finalization `COMMIT` completes | treat client outcome as uncertain, retry stable dedupe/delivery identity, inspect persisted state, and reject stale finalizers |
| Relay process signal | SIGTERM/SIGINT after a subprocess ready barrier | stop admission, honor bounded grace, leave unfinished leases recoverable |

The complete machine-readable fault definitions, barriers, deadlines, recovery actions,
cleanup rules, and evidence classes are in `tests/chaos/scenarios.json`. Destructive
PostgreSQL cases require the explicitly configured disposable test DSN. The local
single-node record still cannot exercise managed-service failover/promotion and does not
substitute for partner incident exercises. Those remain an external prerequisite in the
fault matrix and design-partner readiness record.

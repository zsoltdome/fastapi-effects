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

The local single-node record cannot exercise managed-service failover/promotion and does
not substitute for partner incident exercises. Those are captured by the design-partner
readiness record.

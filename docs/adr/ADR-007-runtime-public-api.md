# ADR-007: Runtime public API and transaction ownership

- Status: Accepted
- Date: 2026-08-30

`MergenUnitOfWork` owns one explicit outer `AsyncSession` transaction. Entry rejects
SQLAlchemy autobegin, an existing transaction, or another Mergen UoW on the session.
Tenant and subject settings are transaction-local and are bound before application SQL.
The host may not commit independently. Normal exit commits; exceptional exit rolls back.

`emit()` is valid only while that UoW is active. It records the event and the complete
original route fanout in the same transaction as application writes. The public domain
API returns detached immutable records and never ORM objects.

The replaceable boundaries are the effect store, clock, UUID source, random source,
authorization resolver, service policy registry, handler-session provider, and metrics
sink. Boundary Contract v1 remains unchanged.

# Unit-of-work lifecycle

These diagrams describe the implemented explicit outer-transaction lifecycle.

## Success

```text
FastAPI dependency      UoW                    AsyncSession/PostgreSQL
       | resolve Principal |                              |
       | create fresh session                             |
       |------------------>| reject active transaction    |
       |                   | begin ---------------------->|
       |                   | SET LOCAL tenant ----------->|
       | application SQL ------------------------------->|
       | emit typed event -> validate/snapshot/insert --->|
       |                   | commit --------------------->|
       |                   | reset context/session state  |
       | close/finalize session                           |
```

## Application exception

```text
begin + bind tenant
application SQL / emit
application raises
UoW rolls back once
UoW resets context and session metadata in finally
dependency finalizes session
original exception propagates
```

No application row, event, or original delivery remains committed.

## Commit failure

```text
begin + bind tenant
application SQL / emit
commit raises
UoW attempts rollback/cleanup without masking commit error
context token and session metadata reset in finally
session provider closes/discards unusable connection
```

A commit error is not reported as success. The caller must treat transaction outcome
as failed/unknown according to SQLAlchemy/driver behavior; FastAPI Effects does not invoke a
sink to compensate.

## Cancellation

```text
begin + bind tenant
application coroutine cancelled
UoW rollback is shielded only as narrowly needed for cleanup
context/session state reset
CancelledError propagates
```

Cancellation is not a delivery-cancellation feature.

## Dependency-finalizer failure

```text
UoW commit or rollback completes
UoW resets its own context/session metadata
host session dependency finalizer raises
finalizer error propagates according to FastAPI dependency semantics
FastAPI Effects does not retain a bound principal
```

## Nesting and savepoints

A FastAPI Effects UoW requires no active outer session transaction and rejects a nested FastAPI Effects
UoW. Application `begin_nested()` savepoints are allowed only after tenant binding;
they do not redefine ownership of the outer transaction or permit emission after UoW
exit.

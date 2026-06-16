# Public API spike

Milestone 1 provides importable, typed shapes to evaluate ergonomics. Security-critical
operations fail closed until Milestone 2.

## Root exports

The intended public surface is limited to:

```text
Mergen
Principal
Event
EffectContext
MergenUnitOfWork
AuthorizationMode
RetryPolicy
selected public exceptions
__version__
```

Repository, ORM model, SQL expression, DBAPI connection, relay-session, and HTTP client
internals are not root exports.

## Documented integration namespaces

The root remains intentionally small. Integration-specific declarations are imported from
their owned namespaces:

```python
from fastapi_mergen.postgres import PostgresStore
from fastapi_mergen.sqlalchemy import MergenUnitOfWork
```

`PostgresStore` is a fail-closed Milestone 1 declaration. Calling its persistence guard
raises `MilestoneNotImplementedError`; it does not imply that schema, RLS, or event
persistence already exists.

## Route declaration

```python
mergen.route(
    event_type="invoice.created",
    route_key="invoice.render_pdf",
    version=1,
).to_handler(
    render_invoice_pdf,
    required_scopes={"invoices:read"},
    authorization="revalidate",
    retry_policy=RetryPolicy(name="default-handler"),
)
```

Registration freezes before serving. Exact event-type matching and explicit
key/version are deliberate. The highest registered version of a stable route key is
active for new emissions; older registered handlers remain available only for
already-snapshotted deliveries. A route key cannot change event type. Wildcard/filter
DSLs are outside the MDP.

## Request unit of work

```python
get_uow = mergen.uow_dependency(get_async_session)

@app.post("/invoices")
async def create_invoice(
    data: InvoiceIn,
    uow: MergenUnitOfWork = Depends(get_uow),
) -> InvoiceOut:
    async with uow:
        ...
```

In `0.0.1`, entering this context raises `MilestoneNotImplementedError` before starting
SQL. The shape is evaluated without pretending that transaction/RLS behavior exists.

## Replaceable protocols

The host can provide principal, authorization, clock, random, handler-session, and
future effect-store implementations through explicit protocols. User code need not
subclass internal implementation classes.

## Rejected surface alternatives

- ambient global `emit()` — hides transaction ownership;
- `@mergen.task` — implies a queue Mergen does not own;
- ORM-object event serialization — unstable and may leak relationships/PII;
- route resolution by mutable function name — unsafe for retries;
- raw authorization-header forwarding — credential leakage/audience risk;
- public repository/SQL types — unnecessarily freezes internals.

# Runtime public API

The Milestone 1 spike has become the narrow typed surface for the M8 core runtime.

## Root exports

The intended public surface is limited to:

```text
FastAPIEffects
Principal
Event
EffectContext
FastAPIEffectsUnitOfWork
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
from fastapi_effects.postgres import PostgresStore
from fastapi_effects.sqlalchemy import FastAPIEffectsUnitOfWork
```

`PostgresStore` persists events and their immutable original delivery set through the
active `FastAPIEffectsUnitOfWork`. Repository and ORM types remain internal.

## Route declaration

```python
fastapi_effects.route(
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
get_uow = fastapi_effects.uow_dependency(get_async_session)


@app.post("/invoices")
async def create_invoice(
    data: InvoiceIn,
    uow: FastAPIEffectsUnitOfWork = Depends(get_uow),
) -> InvoiceOut:
    async with uow:
        ...
```

The context rejects active or nested transactions, binds tenant and subject settings,
and commits or rolls back the application row and effect intent together.

## Replaceable protocols

The host can provide principal, authorization, clock, random, handler-session, and
effect-store implementations through explicit protocols. User code need not
subclass internal implementation classes.

## Rejected surface alternatives

- ambient global `emit()` — hides transaction ownership;
- `@fastapi_effects.task` — implies a queue FastAPI Effects does not own;
- ORM-object event serialization — unstable and may leak relationships/PII;
- route resolution by mutable function name — unsafe for retries;
- raw authorization-header forwarding — credential leakage/audience risk;
- public repository/SQL types — unnecessarily freezes internals.

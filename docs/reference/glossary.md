# Glossary

**Application transaction**  
The outer SQLAlchemy/PostgreSQL transaction owned by `MergenUnitOfWork` and containing
application state plus event/delivery intents.

**Attempt**  
One started execution under one lease token. Attempts are append-only.

**Atomic publication**  
Application rows, event, and every original delivery commit locally together or not at
all.

**Delivery**  
One independently retryable route from an event to one destination.

**Effect**  
Typed immutable deferred intent represented by an event and its delivery routes.

**Effectively-once outcome**  
A consumer outcome achieved by durable deduplication of the stable delivery/message
ID. It is not a generic sender guarantee.

**Event**  
Immutable typed intent and principal/causal provenance committed with application
state.

**Lease token**  
A fresh random capability proving current claim ownership for renewal/finalization.

**Original delivery**  
A delivery selected and inserted during initial event emission; `replay_of` is null.

**Principal**  
Trusted tenant, subject, actor/client, scope, and timestamp context supplied by the
host application.

**Replay**  
An explicit new delivery linked to an immutable original terminal delivery.

**Route snapshot**  
Immutable route key/version, destination, retry, and authorization data captured at
emission.

**Tenant-safe effect**  
A deferred effect whose local intent, tenant, authority provenance, retry identity,
and history remain explicit across execution boundaries.

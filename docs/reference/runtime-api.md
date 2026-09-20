# Runtime API

The supported core path is async FastAPI, SQLAlchemy 2.x `AsyncSession`, PostgreSQL
16–18, and `asyncpg`.

1. Configure a trusted asynchronous principal provider and `PostgresStore` on
   `FastAPIEffects`.
2. Declare exact event routes and freeze registration at startup.
3. Resolve `FastAPIEffects.uow_dependency()` after authentication and session creation.
4. Enter `async with uow`, perform application writes through `uow.session`, and call
   `await uow.emit(Event(...))`.
5. Run the bounded polling relay under the relay role. Handlers obtain fresh
   tenant-bound application sessions from `EffectContext.application_session()`.

The UoW refuses an already active transaction. Publication is atomic locally;
delivery is at least once. Automatic retries retain the delivery ID, while replay
creates a linked new delivery ID.

`verify_webhook()` authenticates the exact body bytes and, by default, accepts an
attempt timestamp no more than 300 seconds old or 300 seconds in the future. Receivers
may pass an aware `now`, `maximum_age`, and `maximum_future_skew` for deterministic
tests or a documented deployment policy. Invalid application configuration raises
`FastAPIEffectsConfigurationError`; malformed external headers return `False`. Freshness does
not replace durable message-ID deduplication.

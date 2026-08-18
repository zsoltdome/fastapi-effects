# Runtime API

The supported core path is async FastAPI, SQLAlchemy 2.x `AsyncSession`, PostgreSQL
16–18, and `asyncpg`.

1. Configure a trusted asynchronous principal provider and `PostgresStore` on
   `Mergen`.
2. Declare exact event routes and freeze registration at startup.
3. Resolve `Mergen.uow_dependency()` after authentication and session creation.
4. Enter `async with uow`, perform application writes through `uow.session`, and call
   `await uow.emit(Event(...))`.
5. Run the bounded polling relay under the relay role. Handlers obtain fresh
   tenant-bound application sessions from `EffectContext.application_session()`.

The UoW refuses an already active transaction. Publication is atomic locally;
delivery is at least once. Automatic retries retain the delivery ID, while replay
creates a linked new delivery ID.

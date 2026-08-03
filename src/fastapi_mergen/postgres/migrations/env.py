"""Alembic environment for programmatic or CLI migration execution."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from fastapi_mergen.sqlalchemy.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_with_connection)
    await connectable.dispose()


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        if not isinstance(supplied, Connection):
            raise TypeError("Alembic connection attribute must be a synchronous Connection.")
        _run_with_connection(supplied)
        return
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

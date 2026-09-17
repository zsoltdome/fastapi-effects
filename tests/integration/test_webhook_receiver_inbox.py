from __future__ import annotations

import asyncio

import pytest
from examples.webhook_receiver.inbox import (
    InboxConflictError,
    apply_once,
    install_inbox_schema,
)
from sqlalchemy import Column, Integer, MetaData, String, Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration

effect_metadata = MetaData()
effects = Table(
    "example_webhook_effect",
    effect_metadata,
    Column("effect_key", String(128), primary_key=True),
    Column("application_count", Integer, nullable=False),
)


async def _install_effect_schema(engine: object) -> None:
    async with engine.begin() as connection:  # type: ignore[attr-defined]
        await connection.run_sync(effect_metadata.create_all)


def _effect(key: str):  # type: ignore[no-untyped-def]
    async def apply(session: AsyncSession) -> None:
        await session.execute(effects.insert().values(effect_key=key, application_count=1))

    return apply


@pytest.mark.asyncio
async def test_postgres_inbox_is_concurrent_restart_safe_and_detects_conflicts(
    test_database: ProvisionedDatabase,
) -> None:
    engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await install_inbox_schema(engine)
        await _install_effect_schema(engine)
        ready = asyncio.Event()
        release = asyncio.Event()

        async def receive(index: int) -> bool:
            async with sessions() as session, session.begin():
                if index == 0:
                    ready.set()
                    await release.wait()
                result = await apply_once(
                    session,
                    source_namespace="endpoint.production",
                    message_id="msg_concurrent",
                    body=b'{"invoice":"42"}',
                    effect=_effect("invoice-42"),
                )
                return result.duplicate

        first = asyncio.create_task(receive(0))
        await ready.wait()
        second = asyncio.create_task(receive(1))
        release.set()
        assert sorted(await asyncio.gather(first, second)) == [False, True]

        await engine.dispose()
        engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session, session.begin():
            restarted = await apply_once(
                session,
                source_namespace="endpoint.production",
                message_id="msg_concurrent",
                body=b'{"invoice":"42"}',
                effect=_effect("must-not-run"),
            )
        assert restarted.duplicate

        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(effects)) == 1

        async with sessions() as session, session.begin():
            with pytest.raises(InboxConflictError, match="conflicts"):
                await apply_once(
                    session,
                    source_namespace="endpoint.production",
                    message_id="msg_concurrent",
                    body=b'{"invoice":"different"}',
                    effect=_effect("must-not-run"),
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_inbox_rollback_does_not_consume_message_id(
    test_database: ProvisionedDatabase,
) -> None:
    engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await install_inbox_schema(engine)
        await _install_effect_schema(engine)

        async def roll_back() -> None:
            async with sessions() as session, session.begin():
                await apply_once(
                    session,
                    source_namespace="endpoint.rollback",
                    message_id="msg_rollback",
                    body=b"body",
                    effect=_effect("rolled-back"),
                )
                raise RuntimeError("controlled rollback")

        with pytest.raises(RuntimeError, match="controlled rollback"):
            await roll_back()

        async with sessions() as session, session.begin():
            result = await apply_once(
                session,
                source_namespace="endpoint.rollback",
                message_id="msg_rollback",
                body=b"body",
                effect=_effect("committed"),
            )
        assert not result.duplicate
        async with sessions() as session:
            keys = set(await session.scalars(select(effects.c.effect_key)))
        assert keys == {"committed"}
    finally:
        await engine.dispose()

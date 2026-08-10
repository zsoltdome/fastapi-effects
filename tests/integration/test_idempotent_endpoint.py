from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.responses import JSONResponse, Response

from fastapi_mergen.core.principal import Principal
from fastapi_mergen.errors import MergenError
from fastapi_mergen.idempotency.api import (
    command_context,
    command_http_exception,
    prepare_command,
)
from fastapi_mergen.postgres.command_schema import install_command_schema
from fastapi_mergen.postgres.roles import RuntimeRoles
from fastapi_mergen.postgres.schema import install_core_schema
from fastapi_mergen.sqlalchemy.models import SCHEMA
from tests.integration.postgres import ProvisionedDatabase

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_fastapi_endpoint_executes_once_and_replays_response(
    test_database: ProvisionedDatabase,
) -> None:
    migration_engine = create_async_engine(test_database.migration_sqlalchemy_dsn)
    app_engine = create_async_engine(test_database.app_sqlalchemy_dsn)
    sessions = async_sessionmaker(app_engine, expire_on_commit=False)
    roles = RuntimeRoles(
        migration=test_database.migration_role,
        application=test_database.app_role,
        relay=test_database.relay_role,
    )
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, subject_id="user:endpoint")
    business_table = f"{SCHEMA}.idempotent_endpoint_business"
    app = FastAPI()

    @app.post("/invoices/{invoice_id}")
    async def create_invoice(invoice_id: str, request: Request) -> Response:
        del invoice_id
        try:
            prepared = await prepare_command(
                request,
                principal=principal,
                route_id="invoice.create",
            )
            payload = await request.json()
            async with sessions() as session:
                context = command_context(
                    session,
                    principal=principal,
                    prepared=prepared,
                )
                async with context:
                    if context.replayed:
                        return context.replay_response()
                    await session.execute(
                        text(
                            f"INSERT INTO {business_table}(tenant_id, invoice_id, amount) "
                            "VALUES (:tenant, :invoice, :amount)"
                        ),
                        {
                            "tenant": tenant_id,
                            "invoice": payload["invoice_id"],
                            "amount": payload["amount"],
                        },
                    )
                    response = JSONResponse(payload, status_code=201, headers={"ETag": '"v1"'})
                    await asyncio.sleep(0.02)
                    await context.complete(response)
                    return response
        except MergenError as exc:
            raise command_http_exception(exc) from exc

    try:
        await install_core_schema(migration_engine, roles=roles)
        await install_command_schema(migration_engine, roles=roles)
        async with migration_engine.begin() as connection:
            await connection.execute(
                text(
                    f"CREATE TABLE {business_table} (tenant_id uuid NOT NULL, "
                    "invoice_id text NOT NULL UNIQUE, amount integer NOT NULL)"
                )
            )
            await connection.execute(
                text(f"GRANT SELECT, INSERT ON {business_table} TO {roles.application}")
            )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test.example",
        ) as client:
            headers = {"Idempotency-Key": "endpoint-command-1"}
            first, second = await asyncio.gather(
                client.post(
                    "/invoices/inv-1?notify=true",
                    headers=headers,
                    json={"invoice_id": "inv-1", "amount": 42},
                ),
                client.post(
                    "/invoices/inv-1?notify=true",
                    headers=headers,
                    json={"amount": 42, "invoice_id": "inv-1"},
                ),
            )
            assert sorted(response.status_code for response in (first, second)) == [201, 201]
            assert first.json() == second.json() == {"invoice_id": "inv-1", "amount": 42}
            assert {
                first.headers.get("idempotency-replayed"),
                second.headers.get("idempotency-replayed"),
            } == {None, "true"}

            conflict = await client.post(
                "/invoices/inv-1?notify=true",
                headers=headers,
                json={"invoice_id": "inv-1", "amount": 99},
            )
            assert conflict.status_code == 409
            assert "endpoint-command-1" not in conflict.text

        async with sessions() as session:
            count = await session.scalar(text(f"SELECT count(*) FROM {business_table}"))
        assert count == 1
    finally:
        await app_engine.dispose()
        await migration_engine.dispose()

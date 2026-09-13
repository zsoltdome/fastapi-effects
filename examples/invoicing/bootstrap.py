"""Create the example's business tables with migration-owner authority."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from fastapi_mergen.postgres import RuntimeRoles

from .app.models import Base


async def bootstrap() -> None:
    dsn = os.getenv("MERGEN_EXAMPLE_MIGRATION_DATABASE_URL")
    if not dsn:
        raise RuntimeError("MERGEN_EXAMPLE_MIGRATION_DATABASE_URL is required.")
    engine = create_async_engine(dsn)
    roles = RuntimeRoles()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            for table in ("invoice", "invoice_renders"):
                await connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                await connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
                await connection.execute(text(f"DROP POLICY IF EXISTS {table}_tenant ON {table}"))
                await connection.execute(
                    text(
                        f"CREATE POLICY {table}_tenant ON {table} FOR ALL TO {roles.application} "
                        "USING (tenant_id = nullif(current_setting('mergen.tenant_id', true), "
                        "'')::uuid) WITH CHECK (tenant_id = "
                        "nullif(current_setting('mergen.tenant_id', true), '')::uuid)"
                    )
                )
                await connection.execute(
                    text(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {roles.application}")
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap())

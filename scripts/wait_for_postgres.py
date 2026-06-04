#!/usr/bin/env python3
"""Wait for a disposable PostgreSQL integration service without leaking its DSN."""

from __future__ import annotations

import argparse
import asyncio
import time


async def wait(dsn: str, timeout_seconds: float) -> None:
    try:
        import asyncpg
    except ImportError as exc:
        raise SystemExit('Install test dependencies with `uv sync --group test`.') from exc

    deadline = time.monotonic() + timeout_seconds
    last_error = "unavailable"
    while time.monotonic() < deadline:
        try:
            connection = await asyncpg.connect(dsn, timeout=2)
        except Exception as exc:  # bounded retry loop; message is not printed
            last_error = type(exc).__name__
            await asyncio.sleep(0.5)
        else:
            try:
                await connection.fetchval("SELECT 1")
            finally:
                await connection.close()
            print("PostgreSQL integration service is ready")
            return
    raise SystemExit(f"PostgreSQL did not become ready: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dsn")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    asyncio.run(wait(args.dsn, args.timeout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

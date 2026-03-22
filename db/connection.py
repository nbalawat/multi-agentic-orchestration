"""
Database connection pool for the User Management API.

Manages an asyncpg connection pool that is initialised once on FastAPI startup
and torn down gracefully on shutdown.  A ``get_db`` async dependency yields a
single acquired connection to route handlers.

Usage
-----
In your FastAPI application::

    from db.connection import init_pool, close_pool, get_db

    @app.on_event("startup")
    async def startup():
        await init_pool()

    @app.on_event("shutdown")
    async def shutdown():
        await close_pool()

    @app.get("/example")
    async def example(conn=Depends(get_db)):
        return await conn.fetchval("SELECT 1")

Environment
-----------
DATABASE_URL
    Full asyncpg-compatible connection string, e.g.
    ``postgresql://user:password@host:port/dbname``
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

import asyncpg
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Module-level pool singleton
_pool: asyncpg.Pool | None = None


async def init_pool(
    dsn: str | None = None,
    min_size: int = 2,
    max_size: int = 10,
) -> None:
    """Create the asyncpg connection pool.

    Parameters
    ----------
    dsn:
        Connection string.  Falls back to the ``DATABASE_URL`` environment
        variable when *None*.
    min_size:
        Minimum number of connections kept open (default ``2``).
    max_size:
        Maximum number of connections in the pool (default ``10``).
    """
    global _pool

    connection_string = dsn or os.environ["DATABASE_URL"]
    _pool = await asyncpg.create_pool(
        connection_string,
        min_size=min_size,
        max_size=max_size,
    )


async def close_pool() -> None:
    """Gracefully close the asyncpg connection pool."""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """FastAPI dependency that yields an acquired database connection.

    Yields
    ------
    asyncpg.Connection
        A connection checked out from the pool for the duration of the request.

    Raises
    ------
    RuntimeError
        If :func:`init_pool` has not been called before the first request.
    """
    if _pool is None:
        raise RuntimeError(
            "Database pool is not initialised. "
            "Call ``await init_pool()`` during application startup."
        )

    async with _pool.acquire() as connection:
        yield connection

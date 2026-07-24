from contextlib import asynccontextmanager
from typing import AsyncGenerator
import asyncpg
from fastapi import FastAPI, Request
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle (DB connection pool)."""
    settings = get_settings()

    app.state.db_pool = await asyncpg.create_pool(
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        host=settings.db_host,
        port=settings.db_port,
        min_size=2,
        max_size=10,
    )

    try:
        yield
    finally:
        await app.state.db_pool.close()


async def get_db_connection(
    request: Request,
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Provide a database connection from the pool for request scope."""
    pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        yield connection
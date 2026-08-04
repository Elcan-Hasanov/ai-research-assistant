from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from fastapi import FastAPI

from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle (DB connection pool)."""
    settings = get_settings()

    app.state.pool = await asyncpg.create_pool(
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        database=settings.db_name,
        host=settings.db_host,
        port=settings.db_port,
        min_size=2,
        max_size=10,
    )

    try:
        yield
    finally:
        await app.state.pool.close()


async def get_standalone_db_connection() -> asyncpg.Connection:
    """Provide a direct database connection for background scripts."""
    settings = get_settings()

    return await asyncpg.connect(
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        database=settings.db_name,
        host=settings.db_host,
        port=settings.db_port,
    )
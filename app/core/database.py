import asyncpg
from pgvector.asyncpg import register_vector

from app.core.config import get_settings


def _connection_kwargs() -> dict:
    """Single source of truth for connection credentials."""
    settings = get_settings()

    return {
        "user": settings.db_user,
        "password": settings.db_password.get_secret_value(),
        "database": settings.db_name,
        "host": settings.db_host,
        "port": settings.db_port,
    }


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register pgvector type codecs on every connection the pool opens."""
    await register_vector(conn)


async def create_db_pool() -> asyncpg.Pool:
    """Create the application-wide connection pool."""
    return await asyncpg.create_pool(
        **_connection_kwargs(),
        min_size=2,
        max_size=10,
        init=_init_connection,
    )


async def create_script_pool(min_size: int = 1, max_size: int = 4) -> asyncpg.Pool:
    """Create a short-lived pool for standalone scripts (ingestion, backfill, measurement)."""
    return await asyncpg.create_pool(
        **_connection_kwargs(),
        min_size=min_size,
        max_size=max_size,
        init=_init_connection,
    )


async def get_standalone_db_connection() -> asyncpg.Connection:
    """Provide a direct connection for the migration runner.

    NOTE: deliberately does NOT register the vector codec. On a fresh database
    the 'vector' type does not exist until migration 002 has run, and
    registering a codec for an unknown type raises at connect time.
    """
    return await asyncpg.connect(**_connection_kwargs())
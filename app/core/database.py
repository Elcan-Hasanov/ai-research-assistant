import asyncpg

from app.core.config import get_settings


async def create_db_pool() -> asyncpg.Pool:
    """Create the application-wide connection pool."""
    settings = get_settings()

    return await asyncpg.create_pool(
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        database=settings.db_name,
        host=settings.db_host,
        port=settings.db_port,
        min_size=2,
        max_size=10,
        command_timeout=30
    )


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
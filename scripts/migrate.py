import asyncio
import logging
from pathlib import Path

from app.core.database import get_standalone_db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)

logger = logging.getLogger(__name__)


async def create_migrations_table(conn) -> None:
    query = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version VARCHAR(255) PRIMARY KEY,
        applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """
    await conn.execute(query)


async def get_applied_migrations(conn) -> set[str]:
    query = "SELECT version FROM schema_migrations;"
    rows = await conn.fetch(query)

    return {row["version"] for row in rows}


def get_all_migrations() -> list[Path]:
    migrations_dir = Path("migrations")

    return sorted(migrations_dir.glob("*.sql"))


async def run_migration(conn, file_path: Path) -> None:
    sql_content = file_path.read_text(encoding="utf-8")

    async with conn.transaction():
        await conn.execute(sql_content)

        query = "INSERT INTO schema_migrations (version) VALUES ($1);"
        await conn.execute(query, file_path.name)


async def main() -> None:
    conn = None

    try:
        conn = await get_standalone_db_connection()
        await create_migrations_table(conn)

        applied_migrations = await get_applied_migrations(conn)
        migration_files = get_all_migrations()

        for migration in migration_files:
            if migration.name in applied_migrations:
                logger.debug("Skipped migration: %s", migration.name)
                continue

            logger.info("Applying migration: %s", migration.name)
            await run_migration(conn, migration)

        logger.info("Database migrations completed successfully.")

    finally:
        if conn is not None:
            await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
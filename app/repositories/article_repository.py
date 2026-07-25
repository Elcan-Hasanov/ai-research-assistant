from datetime import datetime
import asyncpg
from fastapi import Depends

from app.core.database import get_db_connection

class ArticleRepository:
    """Database access layer for article operations."""

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def list_articles(
        self, limit: int = 20, offset: int = 0
    ) -> list[asyncpg.Record]:
        """Fetch paginated articles sorted by publication date descending."""

        query = "SELECT * FROM articles ORDER BY published_at DESC LIMIT $1 OFFSET $2"
        return await self._connection.fetch(query, limit, offset)

    async def get_by_arxiv_id(self, arxiv_id: str) -> asyncpg.Record | None:
        query = "SELECT * FROM articles WHERE arxiv_id = $1"
        return await self._connection.fetchrow(query, arxiv_id)

    async def upsert_article(
        self,
        arxiv_id: str,
        title: str,
        summary: str,
        authors: str,
        categories: str,
        published_at: datetime,
    ) -> None:
        """Insert a new article or update fields if arxiv_id already exists."""

        query = """
        INSERT INTO articles (arxiv_id, title, summary, authors, categories, published_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (arxiv_id) DO UPDATE SET
            title = EXCLUDED.title,
            summary = EXCLUDED.summary,
            authors = EXCLUDED.authors,
            categories = EXCLUDED.categories,
            published_at = EXCLUDED.published_at;
        """
        await self._connection.execute(
            query, arxiv_id, title, summary, authors, categories, published_at
        )


async def get_article_repository(
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ArticleRepository:
    """FastAPI dependency provider for ArticleRepository."""
    return ArticleRepository(conn)
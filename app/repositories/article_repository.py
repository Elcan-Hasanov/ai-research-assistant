from datetime import datetime
import asyncpg


class ArticleRepository:
    """Database access layer for article operations.
    
    Expects an active asyncpg.Connection instance.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._conn = connection

    async def list_articles(
        self, limit: int = 20, offset: int = 0, category: str | None = None
    ) -> list[asyncpg.Record]:
        """Fetch paginated articles sorted by publication date descending."""
        query = """
            SELECT arxiv_id, title, summary, authors, categories, published_at, updated_at
            FROM articles
            WHERE ($1::text IS NULL OR $1 = ANY(categories))
            ORDER BY published_at DESC
            LIMIT $2 OFFSET $3;
        """
        return await self._conn.fetch(query, category, limit, offset)

    async def count_articles(self, category: str | None = None) -> int:
        """Count articles matching the same filter used by list_articles."""
        query = """
            SELECT COUNT(*) FROM articles
            WHERE ($1::text IS NULL OR $1 = ANY(categories));
        """
        return await self._conn.fetchval(query, category)

    async def get_by_arxiv_id(self, arxiv_id: str) -> asyncpg.Record | None:
        query = """
            SELECT arxiv_id, title, summary, authors, categories, published_at, updated_at
            FROM articles
            WHERE arxiv_id = $1
        """
        return await self._conn.fetchrow(query, arxiv_id)

    async def upsert_article(
        self,
        arxiv_id: str,
        title: str,
        summary: str,
        authors: str,
        categories: list[str],
        published_at: datetime,
    ) -> None:
        """Insert a new article or update fields if arxiv_id already exists."""
        query = """
            INSERT INTO articles (arxiv_id, title, summary, authors, categories, published_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (arxiv_id) DO UPDATE SET
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                authors = EXCLUDED.authors,
                categories = EXCLUDED.categories,
                published_at = EXCLUDED.published_at,
                updated_at = NOW();
        """
        await self._conn.execute(
            query, arxiv_id, title, summary, authors, categories, published_at
        )

    async def search_articles(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> list[asyncpg.Record]:
        sql = """
            SELECT
                arxiv_id,
                ts_rank_cd(search_vector, websearch_to_tsquery('english', $1)) AS rank
            FROM articles
            WHERE search_vector @@ websearch_to_tsquery('english', $1)
            ORDER BY rank DESC
            LIMIT $2 OFFSET $3;
        """
        return await self._conn.fetch(sql, query, limit, offset)

    async def count_search_results(self, query: str) -> int:
        """Count articles matching the same full-text query."""
        sql = """
            SELECT COUNT(*) FROM articles
            WHERE search_vector @@ websearch_to_tsquery('english', $1);
        """
        return await self._conn.fetchval(sql, query)
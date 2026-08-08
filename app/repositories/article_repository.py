from datetime import datetime
import asyncpg


class ArticleRepository:
    """Database access layer for article operations."""

    def __init__(self, db: asyncpg.Pool | asyncpg.Connection) -> None:
        self._db = db

    async def list_articles(
        self, limit: int = 20, offset: int = 0, category: str | None = None
    ) -> list[dict]:
        """Fetch paginated articles sorted by publication date descending."""
        query = """
            SELECT arxiv_id, title, summary, authors, categories, published_at, updated_at
            FROM articles
            WHERE ($1::text IS NULL OR $1 = ANY(categories))
            ORDER BY published_at DESC
            LIMIT $2 OFFSET $3;
        """
        rows = await self._db.fetch(query, category, limit, offset)
        return [dict(r) for r in rows]

    async def count_articles(self, category: str | None = None) -> int:
        """Count articles matching the same filter used by list_articles."""
        query = """
            SELECT COUNT(*) FROM articles
            WHERE ($1::text IS NULL OR $1 = ANY(categories));
        """
        return await self._db.fetchval(query, category)

    async def get_by_arxiv_id(self, arxiv_id: str) -> dict | None:
        query = """
            SELECT arxiv_id, title, summary, authors, categories, published_at, updated_at
            FROM articles
            WHERE arxiv_id = $1
        """
        row = await self._db.fetchrow(query, arxiv_id)
        return dict(row) if row is not None else None

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
        await self._db.execute(
            query, arxiv_id, title, summary, authors, categories, published_at
        )

    async def search_articles(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> list[dict]:
        sql = """
            SELECT
                arxiv_id,
                ts_rank_cd(search_vector, websearch_to_tsquery('english', $1)) AS rank
            FROM articles
            WHERE search_vector @@ websearch_to_tsquery('english', $1)
            ORDER BY rank DESC
            LIMIT $2 OFFSET $3;
        """
        rows = await self._db.fetch(sql, query, limit, offset)
        return [dict(r) for r in rows]

    async def count_search_results(self, query: str) -> int:
        """Count articles matching the same full-text query."""
        sql = """
            SELECT COUNT(*) FROM articles
            WHERE search_vector @@ websearch_to_tsquery('english', $1);
        """
        return await self._db.fetchval(sql, query)
    async def fetch_missing_embeddings(self, model_name: str, limit: int) -> list[dict]:
        """Phase 1 — Fetches articles that lack embedding records for the specified model.

        Consuming query behavior: Once written, processed rows automatically exit this
        candidate set in subsequent fetches. Do not use OFFSET.
        """
        query = """
            SELECT a.arxiv_id, a.title, a.summary
            FROM articles a
            LEFT JOIN article_embeddings e
                ON e.arxiv_id = a.arxiv_id AND e.model_name = $1
            WHERE e.arxiv_id IS NULL
            LIMIT $2;
        """
        rows = await self._db.fetch(query, model_name, limit)
        return [dict(r) for r in rows]

    async def fetch_existing_embeddings(
        self, model_name: str, limit: int, offset: int
    ) -> list[dict]:
        """Phase 2 — Fetches existing article embedding records along with their stored hashes.

        Non-consuming query behavior: Updated rows continue to satisfy the query condition
        and remain in the dataset. Pagination via OFFSET is required.
        """
        query = """
            SELECT a.arxiv_id, a.title, a.summary, e.content_hash AS stored_hash
            FROM articles a
            JOIN article_embeddings e
                ON e.arxiv_id = a.arxiv_id AND e.model_name = $1
            ORDER BY a.arxiv_id
            LIMIT $2 OFFSET $3;
        """
        rows = await self._db.fetch(query, model_name, limit, offset)
        return [dict(r) for r in rows]

    async def upsert_embeddings(
        self,
        model_name: str,
        rows: list[tuple[str, str, list[float]]],
    ) -> None:
        """Upserts a batch of embedding records. `rows` expects tuples of (arxiv_id, content_hash, embedding).

        This method does not manage transaction boundaries; callers control transaction scoping
        for atomic writes.
        """
        query = """
            INSERT INTO article_embeddings (arxiv_id, model_name, content_hash, embedding, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (arxiv_id, model_name) DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                embedding = EXCLUDED.embedding,
                updated_at = NOW();
        """
        await self._db.executemany(
            query,
            [(arxiv_id, model_name, content_hash, vector) for arxiv_id, content_hash, vector in rows],
        )

    async def count_missing_embeddings(
        self, model_name: str
    ) -> int:
        """Returns the total number of articles missing embeddings for the target model."""
        query = """
            SELECT COUNT(*)
            FROM articles a
            LEFT JOIN article_embeddings e
                ON e.arxiv_id = a.arxiv_id AND e.model_name = $1
            WHERE e.arxiv_id IS NULL
        """
        return await self._db.fetchval(query, model_name)
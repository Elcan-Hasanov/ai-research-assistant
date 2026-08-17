"""Helpers that put rows into the test database.

Every write here happens inside the caller's open transaction, so nothing
survives the test.
"""

from datetime import datetime, timezone

import asyncpg

DEFAULT_PUBLISHED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
FAKE_CONTENT_HASH = "0" * 64


async def insert_article(
    conn: asyncpg.Connection,
    arxiv_id: str,
    title: str,
    summary: str | None = None,
    authors: str = "A. Author, B. Author",
    categories: list[str] | None = None,
    published_at: datetime | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO articles
            (arxiv_id, title, summary, authors, categories, published_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW());
        """,
        arxiv_id,
        title,
        summary,
        authors,
        categories if categories is not None else [],
        published_at if published_at is not None else DEFAULT_PUBLISHED_AT,
    )


async def insert_embedding(
    conn: asyncpg.Connection,
    arxiv_id: str,
    model_name: str,
    vector: list[float],
    content_hash: str = FAKE_CONTENT_HASH,
) -> None:
    await conn.execute(
        """
        INSERT INTO article_embeddings
            (arxiv_id, model_name, content_hash, embedding, updated_at)
        VALUES ($1, $2, $3, $4, NOW());
        """,
        arxiv_id,
        model_name,
        content_hash,
        vector,
    )
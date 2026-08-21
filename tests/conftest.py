"""Shared test fixtures.

Provides the test database setup, transaction isolation, and deterministic
embedding model used across the test suite.
"""

import asyncio
import hashlib
import math
import os
import random

import pytest

from app.core.config import get_settings
from app.core.database import create_script_pool, get_standalone_db_connection
from app.repositories.article_repository import ArticleRepository
from app.core.llm import CompletionStop, LLMCompletion


TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "arxiv_test")

os.environ["DB_NAME"] = TEST_DB_NAME
get_settings.cache_clear()

EMBEDDING_DIMENSION = get_settings().embedding_dimension

# A real corpus has thousands of rows. If we find more than this, we are
# pointed at the wrong database and must refuse to run.
MAX_ROWS_IN_TEST_DATABASE = 50


async def _check_test_database() -> None:
    conn = await get_standalone_db_connection()
    try:
        tables = await conn.fetchrow(
            """
            SELECT 
                to_regclass('public.articles')::text AS articles,
                to_regclass('public.article_embeddings')::text AS embeddings
            """
        )
        if tables["articles"] is None or tables["embeddings"] is None:
            raise RuntimeError(
                f"Database {TEST_DB_NAME!r} has no schema. Create it once, then "
                f"apply migrations from the repo root:\n"
                f'    $env:DB_NAME = "{TEST_DB_NAME}"\n'
                f"    python -m scripts.migrate\n"
                f'    Remove-Item Env:\\DB_NAME'
            )

        rows = await conn.fetchval("SELECT count(*) FROM articles")
        if rows > MAX_ROWS_IN_TEST_DATABASE:
            raise RuntimeError(
                f"Database {TEST_DB_NAME!r} holds {rows} articles. That is a "
                f"working corpus, not a test database. Refusing to run: these "
                f"tests write rows."
            )
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def test_database_ready() -> None:
    """Deliberately a sync fixture so it can own and close its event loop."""
    asyncio.run(_check_test_database())


@pytest.fixture
async def db_conn():
    """Provide an isolated database connection with automatic rollback."""
    pool = await create_script_pool(min_size=1, max_size=1)
    try:
        async with pool.acquire() as conn:
            transaction = conn.transaction()
            await transaction.start()
            try:
                yield conn
            finally:
                await transaction.rollback()
    finally:
        await pool.close()


@pytest.fixture
def repository(db_conn) -> ArticleRepository:
    return ArticleRepository(db_conn)


def _deterministic_unit_vector(text: str, dimension: int) -> list[float]:
    """Generate a deterministic unit vector unrelated to semantic meaning.

    Identical inputs produce identical vectors without introducing semantic
    similarity.
    """
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    values = [rng.gauss(0.0, 1.0) for _ in range(dimension)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


class FakeEmbeddingModel:
    """Deterministic stand-in for the production embedding model.

    It reproduces the model interface without providing semantic embeddings.
    """

    def __init__(
        self, model_name: str = "fake/test-model", dimension: int | None = None
    ) -> None:
        self._model_name = model_name
        self._dimension = (
            EMBEDDING_DIMENSION if dimension is None else dimension
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode_query(
        self, text: str, normalize: bool = True
    ) -> list[float]:
        return _deterministic_unit_vector(text, self._dimension)

    def encode_documents(
        self, texts: list[str], batch_size: int = 32, normalize: bool = True
    ) -> list[list[float]]:
        return [
            _deterministic_unit_vector(text, self._dimension)
            for text in texts
        ]


@pytest.fixture
def fake_model() -> FakeEmbeddingModel:
    return FakeEmbeddingModel()


class FakeLLMClient:
    """Fake LLM client for testing without network calls."""

    def __init__(self, response: LLMCompletion | None = None) -> None:
        self._response = response or LLMCompletion(
            text="Fake LLM response",
            stop=CompletionStop.COMPLETED,
            input_tokens=10,
            output_tokens=5,
            model="fake/test-llm",
        )

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMCompletion:
        return self._response


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient()
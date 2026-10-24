"""Shared test fixtures and helpers.

Provides the test database setup and its guard, transaction isolation, the
deterministic embedding model and LLM client doubles, the recorded provider
responses, and the --live switch that keeps billed tests out of a normal run.
"""

import asyncio
import hashlib
import json
import math
import os
import random
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.core.config import get_settings
from app.core.database import create_script_pool, get_standalone_db_connection
from app.core.llm import CompletionStop, LLMCompletion
from app.repositories.article_repository import ArticleRepository
from app.repositories.usage_repository import UsageRepository


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


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="also run the tests marked live; they call the real LLM provider and are billed",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the live tests unless --live was given.

    The marker says which tests are live; the option says whether this run may
    spend money. A -m expression cannot do the second job: -m options do not
    combine, so a default -m "not live" in addopts would be replaced by any -m
    on the command line, -m "not db" included.
    """
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="calls the real LLM provider; run with --live")
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skip_live)


@pytest.fixture(scope="session", autouse=True)
def test_database_ready(request: pytest.FixtureRequest) -> None:
    """Check the test database once per session, if a selected test needs it.

    A session that selects no db test, such as -m "not db" or a live-only run,
    neither needs PostgreSQL nor connects to it. Deliberately a sync fixture so
    it can own and close its event loop.
    """
    if not any(item.get_closest_marker("db") for item in request.session.items):
        return
    asyncio.run(_check_test_database())


@pytest.fixture
async def db_conn(request: pytest.FixtureRequest):
    """Provide an isolated database connection with automatic rollback.

    Only a test marked db may use it. The readiness check runs only when a db
    test is selected, so an unmarked test would reach the database unchecked.
    """
    if request.node.get_closest_marker("db") is None:
        pytest.fail(f"{request.node.nodeid} uses db_conn but is not marked db")

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


@pytest.fixture
def usage_repository(db_conn) -> UsageRepository:
    return UsageRepository(db_conn)


RECORDINGS_DIR = Path(__file__).parent / "recordings"


def load_recording(prompt_identifier: str) -> dict:
    """A recorded exchange: the article a real call asked about, and the response body it got.

    scripts/measure_response_variability.py writes recordings. They are
    replaced by recording again, never edited by hand.
    """
    path = RECORDINGS_DIR / f"{prompt_identifier}.json"
    return json.loads(path.read_text(encoding="utf-8"))


async def recorded_attempts(conn) -> list[dict]:
    """Every row in llm_attempts, read with plain SQL: the application has no reader yet."""
    rows = await conn.fetch("SELECT * FROM llm_attempts ORDER BY request_id, attempt")
    return [dict(row) for row in rows]


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
    """Duck-typed stand-in for LLMClient that never touches the network.

    Its job is to define the LLM contract for tests, so its complete()
    signature must track the real one. If it drifts, a service that calls the
    real client will fail against the fake and the fake stops being evidence.

    It records the arguments of every call: a canned response cannot show
    whether the service rendered the right prompt, mapped the right columns,
    or passed the schema at all.

    It fails only on script. Given outcomes, it plays them back one per
    call: a completion is returned, an exception is raised, and a call past
    the end of the script fails the test, so an unplanned extra attempt
    cannot pass unseen. The failure mode arrived with the retry layer, the
    first code whose behaviour depends on what the client raises. Translating
    a provider error into LLMError is still tested in test_llm_client.py,
    against a real AsyncAnthropic over a faked socket; the errors scripted
    here are for the decisions made above the client.
    """

    def __init__(
        self,
        response: LLMCompletion | None = None,
        *,
        outcomes: list[LLMCompletion | Exception] | None = None,
    ) -> None:
        self._response = response or LLMCompletion(
            text="Fake LLM response",
            stop=CompletionStop.COMPLETED,
            input_tokens=10,
            output_tokens=5,
            model="fake/test-llm",
            elapsed_seconds=1.0,
        )
        self._outcomes = None if outcomes is None else list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        response_schema: dict | None = None,
    ) -> LLMCompletion:
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "model": model,
                "system": system,
                "temperature": temperature,
                "response_schema": response_schema,
            }
        )
        if self._outcomes is None:
            return self._response
        if not self._outcomes:
            raise AssertionError(f"FakeLLMClient: call {len(self.calls)} was not in the script")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient()

@pytest.fixture
def api_client():
    from app.main import app
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
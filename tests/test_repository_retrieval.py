import math
import pytest

from app.core.config import get_settings
from tests.factories import insert_article, insert_embedding

# Run these tests against a real PostgreSQL database with the required extensions.
pytestmark = pytest.mark.db


@pytest.fixture
async def seed_search_articles(db_conn):
    """Create a controlled corpus for testing lexical search behavior."""
    await insert_article(
        db_conn,
        arxiv_id="2601.00001",
        title="Quantum Computing Systems",
        summary="Deep dive into quantum algorithms.",
    )
    await insert_article(
        db_conn,
        arxiv_id="2601.00002",
        title="General Computer Science",
        summary="Brief mention of quantum computing.",
    )
    await insert_article(
        db_conn,
        arxiv_id="2601.00003",
        title="Sourdough Bread Baking",
        summary="How to bake sourdough bread at home.",
    )

    return {
        "high_rel": "2601.00001",
        "low_rel": "2601.00002",
        "no_rel": "2601.00003",
    }


async def test_search_articles_filters_non_matching(
    repository, seed_search_articles
):
    """Ensure articles without a lexical match are excluded from results."""
    ids = seed_search_articles

    results = await repository.search_articles(
        query="Quantum", limit=10, offset=0
    )

    returned_ids = {r["arxiv_id"] for r in results}

    assert len(results) == 2
    assert ids["no_rel"] not in returned_ids


async def test_search_articles_orders_by_relevance(
    repository, seed_search_articles
):
    """Ensure lexical search results are ordered by relevance."""
    ids = seed_search_articles

    results = await repository.search_articles(
        query="Quantum", limit=10, offset=0
    )

    assert results[0]["arxiv_id"] == ids["high_rel"]
    assert results[1]["arxiv_id"] == ids["low_rel"]


async def test_search_articles_matches_contract(
    repository, seed_search_articles
):
    """Ensure lexical search returns the fields expected by upstream services."""
    results = await repository.search_articles(
        query="Quantum", limit=1, offset=0
    )

    assert type(results[0]) is dict
    assert set(results[0].keys()) == {"arxiv_id", "rank"}


async def test_count_search_results_returns_matching_count(
    repository, seed_search_articles
):
    """Ensure the result count matches the number of searchable records."""
    count = await repository.count_search_results(query="Quantum")

    assert count == 2


async def test_count_search_results_returns_zero_when_no_match(
    repository, seed_search_articles
):
    """Ensure queries with no matches return a zero count."""
    count = await repository.count_search_results(query="NonExistentTerm")

    assert count == 0


DIMENSION = get_settings().embedding_dimension
MODEL_A = "test/model-a"
MODEL_B = "test/model-b"


def _basis_vector(index: int) -> list[float]:
    """Create a unit vector along a single dimension."""
    vector = [0.0] * DIMENSION
    vector[index] = 1.0
    return vector


def _diagonal_vector(first: int, second: int) -> list[float]:
    """Create a unit vector equally distributed across two dimensions."""
    vector = [0.0] * DIMENSION
    component = 1.0 / math.sqrt(2.0)
    vector[first] = component
    vector[second] = component
    return vector


@pytest.fixture
async def seed_semantic_search(db_conn):
    """Create vectors with known cosine distances for deterministic ordering tests.

    The query vector is e0. This gives predictable distances:
        nearest       e0                -> 0.0
        middle        (e0 + e1)/sqrt(2) -> ~0.2929
        farthest      e1                -> 1.0

    The fourth vector uses the same embedding as the nearest result but
    belongs to a different model, allowing model isolation to be tested.
    """
    rows = [
        ("2601.00001", MODEL_A, _basis_vector(0)),
        ("2601.00002", MODEL_A, _diagonal_vector(0, 1)),
        ("2601.00003", MODEL_A, _basis_vector(1)),
        ("2601.00004", MODEL_B, _basis_vector(0)),
    ]

    for arxiv_id, model_name, vector in rows:
        await insert_article(db_conn, arxiv_id=arxiv_id, title=f"Article {arxiv_id}")
        await insert_embedding(
            db_conn, arxiv_id=arxiv_id, model_name=model_name, vector=vector
        )

    return {
        "nearest": "2601.00001",
        "middle": "2601.00002",
        "farthest": "2601.00003",
        "other_model": "2601.00004",
        "query_vector": _basis_vector(0),
        "model": MODEL_A,
        "other_model_name": MODEL_B,
    }


async def test_semantic_search_orders_by_distance(
    repository, seed_semantic_search
):
    """Ensure semantic search returns results ordered by cosine distance."""
    ids = seed_semantic_search

    results = await repository.semantic_search(
        query_vector=ids["query_vector"], model_name=MODEL_A, limit=10, offset=0,
    )

    assert results[0]["arxiv_id"] == ids["nearest"]
    assert results[1]["arxiv_id"] == ids["middle"]
    assert results[2]["arxiv_id"] == ids["farthest"]


async def test_semantic_search_excludes_other_models(
    repository, seed_semantic_search
):
    """Ensure embeddings from other models do not affect search results."""
    ids = seed_semantic_search

    results = await repository.semantic_search(
        query_vector=ids["query_vector"],
        model_name=ids["model"],
        limit=10,
        offset=0,
    )

    returned_ids = {row["arxiv_id"] for row in results}

    assert len(results) == 3
    assert ids["other_model"] not in returned_ids


async def test_count_embedded_articles_counts_only_the_named_model(
    repository, seed_semantic_search
):
    """Ensure embedding counts are scoped to the requested model."""
    ids = seed_semantic_search

    count = await repository.count_embedded_articles(model_name=ids["model"])

    assert count == 3


async def test_count_embedded_articles_counts_the_second_model(
    repository, seed_semantic_search
):
    """Ensure embeddings are counted independently for different models."""
    ids = seed_semantic_search

    count = await repository.count_embedded_articles(
        model_name=ids["other_model_name"]
    )

    assert count == 1


async def test_semantic_search_returns_arxiv_id_and_distance(
    repository, seed_semantic_search
):
    """Ensure semantic search returns the expected result fields."""
    ids = seed_semantic_search

    results = await repository.semantic_search(
        query_vector=ids["query_vector"], model_name=ids["model"], limit=10, offset=0,
    )

    assert type(results[0]) is dict
    assert set(results[0].keys()) == {"arxiv_id", "distance"}
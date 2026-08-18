import pytest

from app.services.article_service import ArticleService
from tests.factories import insert_article, insert_embedding


pytestmark = pytest.mark.db

QUERY_TEXT = "vector search over scientific abstracts"
OTHER_TEXT = "an unrelated sentence used only to build a third vector"


@pytest.fixture
def service(repository, fake_model) -> ArticleService:
    return ArticleService(repository, fake_model)


@pytest.fixture
async def seed_service_search(db_conn, fake_model):
    """Create vectors with known similarity scores for deterministic tests.

    The identical vector should produce a cosine similarity of 1, while its
    negation should produce -1. A third vector provides an unrelated result.
    """
    query_vector = fake_model.encode_query(QUERY_TEXT)
    opposite_vector = [-value for value in query_vector]
    third_vector = fake_model.encode_query(OTHER_TEXT)

    rows = [
        ("2602.00001", query_vector),
        ("2602.00002", opposite_vector),
        ("2602.00003", third_vector),
    ]

    for arxiv_id, vector in rows:
        await insert_article(db_conn, arxiv_id=arxiv_id, title=f"Article {arxiv_id}")
        await insert_embedding(
            db_conn,
            arxiv_id=arxiv_id,
            model_name=fake_model.model_name,
            vector=vector,
        )

    return {
        "identical": "2602.00001",
        "opposite": "2602.00002",
        "third": "2602.00003",
        "query": QUERY_TEXT,
    }


async def test_semantic_search_scores_identical_vector_as_one(
    service, seed_service_search
):
    ids = seed_service_search

    page = await service.semantic_search(
        query=ids["query"],
        limit=10,
        offset=0,
    )

    identical_item = next(
        item for item in page.items if item.document_id == ids["identical"]
    )
    assert identical_item.score == pytest.approx(1.0, abs=1e-5)
    assert identical_item.method == "semantic"


async def test_semantic_search_scores_opposite_vector_as_minus_one(
    service, seed_service_search
):
    ids = seed_service_search

    page = await service.semantic_search(
        query=ids["query"],
        limit=10,
        offset=0,
    )

    opposite_item = next(
        item for item in page.items if item.document_id == ids["opposite"]
    )
    assert opposite_item.score == pytest.approx(-1.0, abs=1e-5)


async def test_semantic_search_total_is_independent_of_limit(
    service, seed_service_search
):
    ids = seed_service_search

    page = await service.semantic_search(
        query=ids["query"],
        limit=1,
        offset=0,
    )

    assert len(page.items) == 1
    assert page.total == 3
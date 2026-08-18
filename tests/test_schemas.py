import pytest
from pydantic import ValidationError

from app.schemas.article import ArticleResponse
from app.schemas.retrieval import PaginatedResponse, RetrievalResult, SearchParams


def test_search_params_applies_documented_defaults():
    params = SearchParams(q="attention")

    assert params.limit == 20
    assert params.offset == 0


@pytest.mark.parametrize("limit", [0, 101])
def test_search_params_rejects_limit_outside_bounds(limit):
    with pytest.raises(ValidationError):
        SearchParams(q="attention", limit=limit)


def test_search_params_rejects_blank_query():
    with pytest.raises(ValidationError):
        SearchParams(q="")


def test_search_params_rejects_negative_offset():
    with pytest.raises(ValidationError):
        SearchParams(q="attention", offset=-1)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ("", []),
        ("   ", []),
        ("cs.AI", ["cs.AI"]),
        ("cs.AI, cs.LG", ["cs.AI", "cs.LG"]),
        ("cs.AI,  , cs.LG", ["cs.AI", "cs.LG"]),
        (["cs.AI", "cs.LG"], ["cs.AI", "cs.LG"]),
    ],
)
def test_article_response_normalises_categories(raw, expected):
    article = ArticleResponse(arxiv_id="2601.00001", title="T", categories=raw)

    assert article.categories == expected


def test_article_response_absorbs_the_authors_categories_asymmetry():
    """Ensure validators handle both PostgreSQL TEXT and TEXT[] representations.

    Authors are stored as TEXT while categories are stored as TEXT[]. This
    test documents the intentional normalization of both input shapes.
    """
    article = ArticleResponse(
        arxiv_id="2601.00001",
        title="T",
        authors="Ada Lovelace, Alan Turing",
        categories=["cs.AI"],
    )

    assert article.authors == ["Ada Lovelace", "Alan Turing"]
    assert article.categories == ["cs.AI"]


def test_paginated_response_validates_items_against_its_type_parameter():
    page = PaginatedResponse[RetrievalResult](
        items=[{"document_id": "2601.00001", "score": 1.5, "method": "lexical"}],
        total=1,
        limit=20,
        offset=0,
    )

    assert isinstance(page.items[0], RetrievalResult)
    assert page.items[0].document_id == "2601.00001"


def test_paginated_response_rejects_items_that_do_not_match():
    with pytest.raises(ValidationError):
        PaginatedResponse[RetrievalResult](
            items=[{"document_id": "2601.00001"}],
            total=1,
            limit=20,
            offset=0,
        )
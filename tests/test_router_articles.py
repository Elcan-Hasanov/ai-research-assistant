"""What these tests hold still is the wiring: a URL reaching the method that
serves it. The behaviour behind each method is covered a layer down, in
test_service_article.py and the repository tests, and none of that notices
when the route above it disappears.
"""

import pytest

from app.api.dependencies import get_article_service
from app.main import app
from app.schemas.article import ArticleResponse
from app.schemas.retrieval import PaginatedResponse, RetrievalResult


class _RecordingArticleService:
    """Records which method the router dispatched to, and nothing else.

    A stub that only returns canned data cannot answer the question this file
    asks. A request that reaches the wrong handler can still come back 200 —
    deleting the search routes once made /articles/search match
    /articles/{arxiv_id} and answer as a lookup. Only the call record tells
    the two apart.

    Its method signatures track ArticleService exactly. If they drift, the
    router will satisfy this double while failing against the real service.
    """

    def __init__(self):
        self.calls: list[str] = []

    async def list_articles(
        self, limit: int, offset: int, category: str | None = None
    ) -> PaginatedResponse[ArticleResponse]:
        self.calls.append("list_articles")

        return PaginatedResponse[ArticleResponse](
            items=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    async def get_by_arxiv_id(self, arxiv_id: str) -> ArticleResponse:
        self.calls.append("get_by_arxiv_id")

        return ArticleResponse(
            arxiv_id=arxiv_id,
            title="Test Article Title",
        )

    async def search_articles(
        self, query: str, limit: int, offset: int
    ) -> PaginatedResponse[RetrievalResult]:
        self.calls.append("search_articles")

        return PaginatedResponse[RetrievalResult](
            items=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    async def semantic_search(
        self, query: str, limit: int, offset: int
    ) -> PaginatedResponse[RetrievalResult]:
        self.calls.append("semantic_search")

        return PaginatedResponse[RetrievalResult](
            items=[],
            total=0,
            limit=limit,
            offset=offset,
        )


@pytest.fixture
def service():
    stub = _RecordingArticleService()
    app.dependency_overrides[get_article_service] = lambda: stub
    return stub


def test_list_route_reaches_list_articles(api_client, service):
    response = api_client.get("/articles")

    assert response.status_code == 200
    assert service.calls == ["list_articles"]


def test_search_route_reaches_search_articles(api_client, service):
    response = api_client.get("/articles/search", params={"q": "transformers"})

    assert response.status_code == 200
    assert service.calls == ["search_articles"]


def test_semantic_search_route_reaches_semantic_search(api_client, service):
    response = api_client.get("/articles/semantic-search", params={"q": "transformers"})

    assert response.status_code == 200
    assert service.calls == ["semantic_search"]


def test_lookup_route_reaches_get_by_arxiv_id(api_client, service):
    response = api_client.get("/articles/2608.07042")

    assert response.status_code == 200
    assert service.calls == ["get_by_arxiv_id"]
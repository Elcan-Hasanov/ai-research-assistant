import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_generation_service
from app.core.llm import LLMError
from app.core.errors import NotFoundError
from app.main import app
from app.prompts.registry import PromptRenderError
from app.services.generation_service import NoSummaryError


class _StubGenerationService:
    """Stands in for GenerationService at the dependency boundary.

    The service is not under test here — the router's and the handler's
    translation of what it returns or raises is.
    """

    def __init__(self, *, result=None, error=None):
        self._result = result
        self._error = error

    async def extract_facts(self, arxiv_id: str):
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture
def api_client():
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _serve(stub: _StubGenerationService) -> None:
    app.dependency_overrides[get_generation_service] = lambda: stub


# ============================================================================
# Category -> HTTP status. One test per category: the mapping from error type
# to category is already pinned in test_error_taxonomy.py, and at this layer
# nothing distinguishes two types that share a category.
# ============================================================================

def test_internal_failures_become_500(api_client):
    """PromptRenderError sits two levels below AppError, so this also proves
    the handler is found by walking the full MRO, not just the direct base."""
    error = PromptRenderError("variable mismatch")
    _serve(_StubGenerationService(error=error))

    response = api_client.post("/articles/2608.07042/facts")

    assert response.status_code == 500
    assert response.json()["detail"] == error.public_message


def test_upstream_failures_become_503(api_client):
    error = LLMError("LLM request failed", status_code=429, provider_error="RateLimitError")
    _serve(_StubGenerationService(error=error))

    response = api_client.post("/articles/2608.07042/facts")

    assert response.status_code == 503
    assert response.json()["detail"] == error.public_message


def test_unusable_source_failures_become_422(api_client):
    error = NoSummaryError("Article summary is missing or empty.")
    _serve(_StubGenerationService(error=error))

    response = api_client.post("/articles/2608.07042/facts")

    assert response.status_code == 422
    assert response.json()["detail"] == error.public_message


def test_missing_article_becomes_404(api_client):
    """Not found is the fourth category rather than a router-level special
    case, so it reaches the caller through the same handler as every other
    failure. The id is echoed back because it came from the caller's own URL."""
    error = NotFoundError(arxiv_id="9999.99999")
    _serve(_StubGenerationService(error=error))

    response = api_client.post("/articles/9999.99999/facts")

    assert response.status_code == 404
    assert response.json()["detail"] == "Article not found: 9999.99999"


# ============================================================================
# The one path that do not go through app_error_handler
# ============================================================================

def test_successful_extraction_still_returns_200(api_client):
    facts = {
        "problem": "p",
        "contributions": ["c"],
        "evaluated": True,
    }
    _serve(_StubGenerationService(result=facts))

    response = api_client.post("/articles/2608.07042/facts")

    assert response.status_code == 200
    assert response.json()["problem"] == "p"
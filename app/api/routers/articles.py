from fastapi import APIRouter, Depends

from app.api.dependencies import get_article_service, get_generation_service
from app.generation.extraction import PaperFacts
from app.services.generation_service import GenerationService
from app.schemas.article import ArticleFilterParams, ArticleResponse
from app.schemas.retrieval import PaginatedResponse, RetrievalResult, SearchParams
from app.services.article_service import ArticleService

router = APIRouter(prefix="/articles", tags=["Articles"])


@router.get("", response_model=PaginatedResponse[ArticleResponse])
async def list_articles(
    params: ArticleFilterParams = Depends(),
    service: ArticleService = Depends(get_article_service),
) -> PaginatedResponse[ArticleResponse]:
    """Return a paginated envelope of articles with optional filtering."""

    return await service.list_articles(
        limit=params.limit,
        offset=params.offset,
        category=params.category,
    )


@router.get("/search", response_model=PaginatedResponse[RetrievalResult])
async def search_articles(
    params: SearchParams = Depends(),
    service: ArticleService = Depends(get_article_service),
) -> PaginatedResponse[RetrievalResult]:
    """Lexical (keyword) search via PostgreSQL full-text search."""

    return await service.search_articles(
        query=params.q,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/semantic-search", response_model=PaginatedResponse[RetrievalResult])
async def semantic_search_articles(
    params: SearchParams = Depends(),
    service: ArticleService = Depends(get_article_service),
) -> PaginatedResponse[RetrievalResult]:
    """Semantic (vector) search via pgvector cosine distance."""

    return await service.semantic_search(
        query=params.q,
        limit=params.limit,
        offset=params.offset,
    )


@router.get(
    "/{arxiv_id}",
    response_model=ArticleResponse,
    responses={
        404: {"description": "No article answers to that id."},
        500: {"description": "The request failed for a reason the caller cannot act on."},
    },
)
async def get_article_by_id(
    arxiv_id: str,
    service: ArticleService = Depends(get_article_service),
) -> ArticleResponse:
    """Fetch a single article by its arXiv id."""
    return await service.get_by_arxiv_id(arxiv_id)


@router.post(
    "/{arxiv_id}/facts",
    response_model=PaperFacts,
    responses={
        404: {"description": "Article not found."},
        422: {"description": "The article cannot be turned into structured facts."},
        500: {"description": "The request failed for a reason the caller cannot act on."},
        503: {"description": "The language model service is temporarily unavailable."},
    },
)
async def extract_article_facts(
    arxiv_id: str,
    service: GenerationService = Depends(get_generation_service),
) -> PaperFacts:
    """Extract structured facts from one article using the LLM."""
    return await service.extract_facts(arxiv_id)
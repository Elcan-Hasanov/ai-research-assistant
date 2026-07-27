from fastapi import APIRouter, Depends, HTTPException

from app.repositories.article_repository import (
    ArticleRepository,
    get_article_repository,
)
from app.schemas.article import ArticleFilterParams, ArticleResponse
from app.repositories.article_repository import ArticleRepository

router = APIRouter(prefix="/articles", tags=["Articles"])


@router.get("", response_model=list[ArticleResponse])
async def list_articles(
    params: ArticleFilterParams = Depends(),
    repo: ArticleRepository = Depends(get_article_repository),
) -> list[ArticleResponse]:
    """Return a paginated list of articles with optional filtering."""

    records = await repo.list_articles(
        limit=params.limit,
        offset=params.offset,
        category=params.category,
    )

    return [ArticleResponse(**dict(record)) for record in records]


@router.get("/{arxiv_id}", response_model=ArticleResponse)
async def get_article_by_id(
    arxiv_id: str,
    repo: ArticleRepository = Depends(get_article_repository),
) -> ArticleResponse:

    record = await repo.get_by_arxiv_id(arxiv_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Article with arxiv_id '{arxiv_id}' not found",
        )

    return ArticleResponse(**dict(record))
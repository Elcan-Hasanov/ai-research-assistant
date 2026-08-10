import asyncpg
from fastapi import Depends, Request

from app.core.embedding import EmbeddingModel
from app.repositories.article_repository import ArticleRepository
from app.services.article_service import ArticleService


async def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


async def get_embedding_model(request: Request) -> EmbeddingModel:
    return request.app.state.embedding_model


async def get_article_repository(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> ArticleRepository:
    return ArticleRepository(pool)


async def get_article_service(
    repo: ArticleRepository = Depends(get_article_repository),
    model: EmbeddingModel = Depends(get_embedding_model),
) -> ArticleService:
    return ArticleService(repo, model)
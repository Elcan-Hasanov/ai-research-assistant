import asyncpg
from fastapi import Depends, Request

from app.repositories.article_repository import ArticleRepository
from app.services.article_service import ArticleService


def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


def get_article_repository(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> ArticleRepository:
    return ArticleRepository(pool)


def get_article_service(
    repo: ArticleRepository = Depends(get_article_repository),
) -> ArticleService:
    return ArticleService(repo)
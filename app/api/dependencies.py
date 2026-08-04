from typing import AsyncGenerator
import asyncpg
from fastapi import Depends, Request

from app.repositories.article_repository import ArticleRepository
from app.services.article_service import ArticleService


def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


async def get_article_repository(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> AsyncGenerator[ArticleRepository, None]:

    async with pool.acquire() as connection:
        yield ArticleRepository(connection)


def get_article_service(
    repo: ArticleRepository = Depends(get_article_repository),
) -> ArticleService:
    return ArticleService(repo)
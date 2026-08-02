from app.repositories.article_repository import ArticleRepository
from app.schemas.article import ArticleResponse
from app.schemas.retrieval import PaginatedResponse


class ArticleService:

    def __init__(self, repository: ArticleRepository) -> None:
        self._repository = repository

    async def list_articles(
        self, limit: int, offset: int, category: str | None = None
    ) -> PaginatedResponse[ArticleResponse]:
        
        records = await self._repository.list_articles(
            limit=limit, offset=offset, category=category
        )
        total = await self._repository.count_articles(category=category)

        items = [ArticleResponse(**dict(record)) for record in records]

        return PaginatedResponse[ArticleResponse](
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_by_arxiv_id(self, arxiv_id: str) -> ArticleResponse | None:
        record = await self._repository.get_by_arxiv_id(arxiv_id)

        if record is None:
            return None

        return ArticleResponse(**dict(record))
from app.repositories.article_repository import ArticleRepository
from app.schemas.article import ArticleResponse
from app.schemas.retrieval import PaginatedResponse, RetrievalResult
from app.core.embedding import EmbeddingModel
import asyncio

class ArticleService:
    """Orchestrates article retrieval and maps persistence records onto API contracts."""

    def __init__(self, repository: ArticleRepository, model: EmbeddingModel) -> None:
        self._repository = repository
        self._model = model

    async def list_articles(
        self, limit: int, offset: int, category: str | None = None
    ) -> PaginatedResponse[ArticleResponse]:
        
        records = await self._repository.list_articles(
            limit=limit, offset=offset, category=category
        )
        total = await self._repository.count_articles(category=category)

        items = [ArticleResponse(**record) for record in records]

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

        return ArticleResponse(**record)

    async def search_articles(
        self, query: str, limit: int, offset: int
    ) -> PaginatedResponse[RetrievalResult]:
        """Lexical (keyword) search. RetrievalResult.method = 'lexical'."""

        records = await self._repository.search_articles(
            query=query, limit=limit, offset=offset
        )
        total = await self._repository.count_search_results(query=query)

        items = [
            RetrievalResult(
                document_id=record["arxiv_id"],
                score=record["rank"],
                method="lexical",
            )
            for record in records
        ]

        return PaginatedResponse[RetrievalResult](
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def semantic_search(
        self, query: str, limit: int, offset: int
    ) -> PaginatedResponse[RetrievalResult]:
        
        query_vector = await asyncio.to_thread(self._model.encode_query, query)

        raw_results = await self._repository.semantic_search(
            query_vector, self._model.model_name, limit, offset
        )

        total = await self._repository.count_embedded_articles(self._model.model_name)

        items = [
            RetrievalResult(
                document_id=row["arxiv_id"],
                score=1.0 - row["distance"],
                method="semantic",
            )
            for row in raw_results
        ]

        return PaginatedResponse[RetrievalResult](
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )
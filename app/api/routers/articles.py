from fastapi import APIRouter, Depends

from app.repositories.article_repository import (
    ArticleRepository,
    get_article_repository,
)
from app.schemas.article import ArticleFilterParams, ArticleResponse

# 1. Yönlendirici Nesnesi (Router)
router = APIRouter(prefix="/articles", tags=["Articles"])


# 2. Endpoint Dekoratörü ve Fonksiyon Tanımı
@router.get("", response_model=list[ArticleResponse])
async def list_articles(
    params: ArticleFilterParams = Depends(),
    repo: ArticleRepository = Depends(get_article_repository),
) -> list[ArticleResponse]:
    """Sayfalanmış ve filtrelenebilir makale listesini döner."""

    # 3. Repository üzerinden veritabanı sorgusunu çalıştırıyoruz
    records = await repo.list_articles(
        limit=params.limit,
        offset=params.offset,
        category=params.category,
    )

    # 4. Veritabanından gelen ham Record nesnelerini DTO modeline dönüştürüyoruz
    return [ArticleResponse(**dict(record)) for record in records]
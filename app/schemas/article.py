from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class ArticleResponse(BaseModel):
    arxiv_id: str
    title: str
    summary: str | None = None
    authors: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("authors", "categories", mode="before")
    def validate_comma_separated_to_list(
        cls, v: str | list | None
    ) -> list[str]:
        # 1. Veritabanından NULL gelirse güvenle boş liste dön
        if v is None:
            return []

        # 2. Virgülle ayrılmış string gelirse parçala
        if isinstance(v, str):
            cleaned_v = v.strip()
            if not cleaned_v:
                return []
            return [
                item.strip() for item in cleaned_v.split(",") if item.strip()
            ]

        return v


class ArticleFilterParams(BaseModel):
    category: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
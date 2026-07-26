from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class ArticleResponse(BaseModel):
    title: str
    authors: list[str]
    arxiv_id: str
    summary: str
    published_at: datetime
    categories: list[str]

    @field_validator("authors", "categories", mode="before")
    def validate_comma_separated_to_list(cls, v: str | list) -> list[str]:

        if isinstance(v, str):
            cleaned_v = v.strip()
            if not cleaned_v: 
                return []
            return [item.strip() for item in cleaned_v.split(",") if item.strip()]
        return v

class ArticleFilterParams(BaseModel):
    category: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
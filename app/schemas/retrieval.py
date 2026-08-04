from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class RetrievalResult(BaseModel):

    document_id: str
    score: float
    method: str


class PaginatedResponse(BaseModel, Generic[T]):

    items: list[T]
    total: int
    limit: int
    offset: int


class SearchParams(BaseModel):

    q: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
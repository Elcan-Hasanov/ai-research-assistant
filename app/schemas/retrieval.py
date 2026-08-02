from typing import Generic, TypeVar

from pydantic import BaseModel

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
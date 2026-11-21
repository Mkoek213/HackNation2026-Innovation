from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SyncMode(StrEnum):
    sync = "sync"
    merge = "merge"


class ErrorItem(BaseModel):
    type: str = Field(examples=["not_found"])
    loc: list[str | int] = Field(examples=[["path", "id"]])
    msg: str = Field(examples=["User with params {'id': 1} was not found."])
    input: Any = Field(default=None, examples=[None])
    ctx: dict[str, Any] | None = Field(default=None, examples=[None])


class ErrorResponse(BaseModel):
    detail: list[ErrorItem]


class Unauthorized(ErrorResponse):
    pass


class Forbidden(ErrorResponse):
    pass


class Post(BaseModel):
    detail: str = Field(examples=["Created."])


class Put(BaseModel):
    detail: str = Field(examples=["Updated."])


class Delete(BaseModel):
    deleted: int = Field(ge=0, examples=[1])
    detail: str = Field(examples=["Deleted User."])


class ItemList(BaseModel, Generic[T]):
    total: int = Field(ge=0, examples=[1])
    items: list[T]


class BatchResult(BaseModel, Generic[T]):
    items: list[T]
    created: int = Field(ge=0, examples=[1])
    updated: int = Field(ge=0, examples=[0])
    unchanged: int = Field(ge=0, examples=[0])
    deleted: int = Field(ge=0, examples=[0])


def _response(description: str) -> dict[str, Any]:
    return {"model": ErrorResponse, "description": description}


UNAUTHORIZED = _response("Not authenticated")
FORBIDDEN = _response("Not enough permissions")
NOT_FOUND = _response("Resource not found")
CONFLICT = _response("Conflict with current state")

from dataclasses import dataclass
from typing import Annotated, AsyncIterator

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import sessionmanager


async def get_db() -> AsyncIterator[AsyncSession]:
    if sessionmanager.session_maker is None:
        raise RuntimeError("DatabaseSessionManager is not initialized")
    async with sessionmanager.session_maker() as session:
        yield session


DatabaseDep = Annotated[AsyncSession, Depends(get_db)]


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class Pagination:
    """Page selection for list endpoints, passed on to ``CRUDRepo.get_all(limit=, offset=)``.
    ``ItemList.total`` stays the unpaginated count, so clients can compute the number of pages."""
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0


def get_pagination(
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Maximum number of items."),
        offset: int = Query(0, ge=0, description="Number of items to skip."),
) -> Pagination:
    """Reads ``?limit=`` (default 20, max 100) and ``?offset=`` (default 0); out-of-range values give 422."""
    return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]

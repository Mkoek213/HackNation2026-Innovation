"""User-owned matters with compare-and-swap writes shared by the API and the workspace agent."""
import datetime as dt
from typing import Any

from sqlalchemy import func, select, update

from app.exceptions import NotFoundError
from app.models import Matter
from app.schemas.default import ItemList
from app.schemas.matter import MatterModel, MatterSummary
from app.utils.crud_repo import CRUDRepo


def now():
    return dt.datetime.now(dt.timezone.utc)


class MatterRepo(CRUDRepo[Matter, MatterModel]):
    async def owned(self, user_id: int, matter_id: int, *, lock=False) -> Matter:
        """:raises NotFoundError: missing, or another user's matter (its existence is not revealed)."""
        query = select(Matter).where(Matter.id == matter_id, Matter.user_id == user_id)
        query = query.with_for_update() if lock else query
        matter = await self.db.scalar(query.execution_options(populate_existing=True))
        if matter is None:
            raise NotFoundError(resource="Matter", key={"id": matter_id}, loc=("path", "matter_id"))
        return matter

    async def mine(self, user_id: int, *, limit: int | None = None, offset: int = 0) -> ItemList[MatterSummary]:
        """The user's matters, most recently updated first."""
        query = (select(Matter).where(Matter.user_id == user_id)
                 .order_by(Matter.updated_at.desc(), Matter.id.desc()).offset(offset).limit(limit))
        total = await self.db.scalar(select(func.count()).select_from(Matter).where(Matter.user_id == user_id))
        items = (await self.db.scalars(query)).all()
        return ItemList[MatterSummary](total=total, items=[*items])

    async def linked(self, user_id: int, conversation_id: int) -> list[Matter]:
        query = (select(Matter).where(Matter.user_id == user_id, Matter.conversation_id == conversation_id)
                 .order_by(Matter.updated_at.desc(), Matter.id.desc()).limit(20))
        return [*(await self.db.scalars(query)).all()]

    async def add(self, user_id: int, *, autocommit: bool = True, **values: Any) -> Matter:
        stamp = now()
        matter = Matter(user_id=user_id, revision=1, created_at=stamp, updated_at=stamp, **values)
        self.db.add(matter)
        await (self.db.commit() if autocommit else self.db.flush())
        await self.db.refresh(matter)
        return matter

    async def write(self, user_id: int, matter_id: int, expected_revision: int, *, autocommit: bool = True,
                    **changes: Any) -> tuple[Matter, bool]:
        """
        Compare-and-swap: applies `changes` only when the stored revision is still `expected_revision`,
        then increments the revision. Returns (current matter, written); a stale revision writes nothing.
        :raises NotFoundError: missing, or another user's matter.
        """
        written = await self.db.execute(update(Matter).where(
            Matter.id == matter_id, Matter.user_id == user_id, Matter.revision == expected_revision,
        ).values(**changes, revision=Matter.revision + 1, updated_at=now()))
        await (self.db.commit() if autocommit else self.db.flush())
        return await self.owned(user_id, matter_id), bool(written.rowcount)

    async def link(self, matter: Matter, conversation_id: int, *, autocommit: bool = True) -> None:
        """Thread link only; not a content edit, so the revision stays."""
        await self.db.execute(update(Matter).where(Matter.id == matter.id).values(conversation_id=conversation_id))
        await (self.db.commit() if autocommit else self.db.flush())

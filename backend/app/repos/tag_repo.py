from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.exceptions import DuplicateError
from app.models import Subtag, Tag
from app.schemas.tag import SubtagCreate, SubtagModel, SubtagUpdate, TagCreate, TagModel, TagUpdate
from app.utils.crud_repo import CRUDRepo


class TagRepo(CRUDRepo[Tag, TagModel]):
    protect_on_delete = ("subtags", "projects", "conversation_tags")

    async def get_all_nested(self) -> Sequence[Tag]:
        """All tags ordered by name, with their subtags loaded (the dictionary is small, not paginated)."""
        # populate_existing refreshes subtag collections already loaded earlier in the same session.
        query = (
            select(Tag)
            .options(selectinload(Tag.subtags))
            .order_by(Tag.name, Tag.id)
            .execution_options(populate_existing=True)
        )
        return (await self.db.scalars(query)).all()

    async def _assert_name_free(self, name: str, *, exclude_id: int | None = None) -> None:
        existing = await self.db.scalar(select(Tag).where(Tag.name == name))
        if existing is not None and existing.id != exclude_id:
            raise DuplicateError(resource="Tag", field="name", value=name)

    async def create_tag(self, tag: TagCreate, *, autocommit: bool = True) -> Tag:
        await self._assert_name_free(tag.name)
        return await self.create(tag, autocommit=autocommit)

    async def update_tag(self, tag: TagUpdate, *, autocommit: bool = True, **kwargs) -> Tag:
        data = tag.model_dump_null()
        if "name" in data:
            await self.get_one(key_loc="path", **kwargs)
            await self._assert_name_free(data["name"], exclude_id=kwargs.get("id"))
        return await self.update(data, key_loc="path", autocommit=autocommit, **kwargs)


class SubtagRepo(CRUDRepo[Subtag, SubtagModel]):
    protect_on_delete = ("projects", "conversation_tags")

    async def _assert_name_free(self, tag_id: int, name: str, *, exclude_id: int | None = None) -> None:
        query = select(Subtag).where(Subtag.tag_id == tag_id, Subtag.name == name)
        existing = await self.db.scalar(query)
        if existing is not None and existing.id != exclude_id:
            raise DuplicateError(resource="Subtag", field="name", value=name)

    async def create_subtag(self, tag_id: int, subtag: SubtagCreate, *, autocommit: bool = True) -> Subtag:
        """Creates a subtag under `tag_id`. Raises 404 when the tag does not exist, 409 on a duplicate name in that tag."""
        await TagRepo(self.db).get_one(id=tag_id, key_loc="path")
        await self._assert_name_free(tag_id, subtag.name)
        return await self.create(subtag, tag_id=tag_id, autocommit=autocommit)

    async def update_subtag(self, subtag: SubtagUpdate, *, autocommit: bool = True, **kwargs) -> Subtag:
        data = subtag.model_dump_null()
        if "name" in data:
            current = await self.get_one(key_loc="path", **kwargs)
            await self._assert_name_free(current.tag_id, data["name"], exclude_id=current.id)
        return await self.update(data, key_loc="path", autocommit=autocommit, **kwargs)

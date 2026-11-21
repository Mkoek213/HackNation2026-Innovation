from typing import Any

from sqlalchemy import Select, func, select

from app.exceptions import ConflictError, DomainErrorGroup, ForbiddenError, NotFoundError, ValidationError
from app.models import Idea, IdeaStage, IdeaStatus, Location, Tag, User
from app.schemas.default import Delete, ItemList
from app.schemas.idea import IdeaCreate, IdeaModel, IdeaUpdate
from app.utils.crud_repo import CRUDRepo


class IdeaRepo(CRUDRepo[Idea, IdeaModel]):

    @staticmethod
    def _filtered(
            query: Select,
            *,
            status: IdeaStatus | None = None,
            author_id: int | None = None,
            tag_id: int | None = None,
            stage: IdeaStage | None = None,
    ) -> Select:
        if status is not None:
            query = query.where(Idea.status == status)
        if author_id is not None:
            query = query.where(Idea.author_id == author_id)
        if tag_id is not None:
            query = query.where(Idea.tag_id == tag_id)
        if stage is not None:
            query = query.where(Idea.stage == stage)
        return query

    async def search(
            self,
            *,
            status: IdeaStatus | None = None,
            author_id: int | None = None,
            tag_id: int | None = None,
            stage: IdeaStage | None = None,
            limit: int | None = None,
            offset: int = 0,
    ) -> ItemList[IdeaModel]:
        """Ideas matching all given filters, newest first; `total` is the unpaginated count."""
        filters = dict(status=status, author_id=author_id, tag_id=tag_id, stage=stage)
        query = self._filtered(select(Idea), **filters).order_by(Idea.id.desc())
        query = query.offset(offset).limit(limit)
        total = await self.db.scalar(self._filtered(select(func.count()).select_from(Idea), **filters))
        items = (await self.db.scalars(query)).all()
        return ItemList[IdeaModel](total=total, items=[*items])

    async def _assert_references(self, data: dict[str, Any]) -> None:
        """:raises DomainErrorGroup: (422) `tag_id` or `location_id` points to a missing row."""
        errors = []
        for field, model in (("tag_id", Tag), ("location_id", Location)):
            value = data.get(field)
            if value is not None and await self.db.get(model, value) is None:
                errors.append(ValidationError(
                    msg=f"{model.__name__} with id {value} does not exist.",
                    loc=("body", field),
                    input_=value,
                ))
        if errors:
            raise DomainErrorGroup(errors)

    @staticmethod
    def _can_manage(user: User | None, idea: Idea) -> bool:
        return user is not None and (user.is_admin or user.id == idea.author_id)

    async def create_idea(self, author: User, idea: IdeaCreate, *, autocommit: bool = True) -> Idea:
        """Creates an idea of `author` with status `submitted`.
        :raises DomainErrorGroup: (422) unknown `tag_id` / `location_id`."""
        await self._assert_references(idea.model_dump())
        obj = await self.create(idea, author_id=author.id, status=IdeaStatus.submitted, autocommit=autocommit)
        await self.db.refresh(obj)  # loads the server-side created_at
        return obj

    async def get_visible(self, idea_id: int, user: User | None) -> Idea:
        """A published idea, or any idea of its author / the admin.
        :raises NotFoundError: missing, or not visible to `user` (its existence is not revealed)."""
        idea = await self.get_one(id=idea_id, key_loc="path", quiet=True)
        if idea is None or (idea.status != IdeaStatus.published and not self._can_manage(user, idea)):
            raise NotFoundError(resource="Idea", key={"id": idea_id}, loc=("path", "idea_id"))
        return idea

    async def get_managed(self, idea_id: int, user: User) -> Idea:
        """An idea that `user` may edit or delete: their own, or any for the admin.
        :raises NotFoundError: missing.
        :raises ForbiddenError: someone else's idea."""
        idea = await self.get_one(id=idea_id, key_loc="path")
        if not self._can_manage(user, idea):
            raise ForbiddenError(msg="You do not have access to this resource.", loc=("path", "idea_id"))
        return idea

    async def update_idea(self, idea_id: int, idea: IdeaUpdate, user: User, *, autocommit: bool = True) -> Idea:
        """
        The author edits the content while the idea is `submitted`; the admin edits anything, including `status`.
        :raises NotFoundError: missing idea.
        :raises ForbiddenError: someone else's idea, or a non-admin setting `status`.
        :raises ConflictError: the author edits an idea that is no longer `submitted`.
        :raises DomainErrorGroup: (422) unknown `tag_id` / `location_id`.
        """
        current = await self.get_managed(idea_id, user)
        data = idea.model_dump_null()
        if not user.is_admin:
            if "status" in data:
                raise ForbiddenError(msg="Only the admin can change the status of an idea.", loc=("body", "status"))
            if current.status != IdeaStatus.submitted:
                raise ConflictError(
                    f"Only submitted ideas can be edited; this one is {current.status.value}.",
                    loc=("path", "idea_id"),
                )
        await self._assert_references(data)
        return await self.update(data, key_loc="path", autocommit=autocommit, id=idea_id)

    async def delete_idea(self, idea_id: int, user: User, *, autocommit: bool = True) -> Delete:
        """
        The author or the admin deletes an idea, whatever its status.
        :raises NotFoundError: missing idea.
        :raises ForbiddenError: someone else's idea.
        """
        await self.get_managed(idea_id, user)
        return await self.delete_one(id=idea_id, key_loc="path", autocommit=autocommit)

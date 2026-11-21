import datetime as dt
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, DependencyUnavailable, DuplicateError, NotFoundError
from app.models import (
    ApplicationSource,
    ApplicationStatus,
    Tag,
    TesterApplication,
    User,
    VolunteerProfile,
    VolunteerTag,
)
from app.modules.knowledge import InnovationNotFound, KnowledgeUnavailable, get_knowledge_service
from app.schemas.default import Delete, ItemList
from app.schemas.tester_application import (
    TesterApplicationAdminModel,
    TesterApplicationAssign,
    TesterApplicationCreate,
    TesterApplicationModel,
)
from app.schemas.volunteer import VolunteerLabel

logger = logging.getLogger(__name__)


async def innovation_title(innovation_id: str, loc: tuple = ("body", "innovation_id")) -> str:
    """:raises NotFoundError: the knowledge base has no such innovation.
    :raises DependencyUnavailable: the knowledge base is not configured or reachable."""
    try:
        service = await get_knowledge_service()
        return (await service.get(innovation_id)).title
    except InnovationNotFound:
        raise NotFoundError(resource="Innovation", key={"id": innovation_id}, loc=loc) from None
    except KnowledgeUnavailable:
        raise DependencyUnavailable(msg="The knowledge base is unavailable, try again later.", loc=loc) from None


async def innovation_titles(ids: set[str]) -> dict[str, str]:
    """Titles of the given innovations in one knowledge-base read; missing ones are left out."""
    if not ids:
        return {}
    try:
        service = await get_knowledge_service()
        return {item.id: item.title for item in await service.list_innovations() if item.id in ids}
    except Exception:  # Titles are cosmetic: callers fall back to the slug.
        logger.warning("Could not resolve innovation titles for tester applications.", exc_info=True)
        return {}


class TesterApplicationRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _fields(application: TesterApplication, titles: dict[str, str]) -> dict:
        return dict(
            id=application.id, innovation_id=application.innovation_id,
            innovation_title=titles.get(application.innovation_id, application.innovation_id),
            status=application.status, source=application.source, message=application.message,
            decided_at=application.decided_at, created_at=application.created_at, updated_at=application.updated_at,
        )

    async def _admin_models(self, rows: list[tuple[TesterApplication, VolunteerProfile]],
                            titles: dict[str, str] | None = None) -> list[TesterApplicationAdminModel]:
        if titles is None:
            titles = await innovation_titles({application.innovation_id for application, _ in rows})
        user_ids = {profile.user_id for _, profile in rows}
        tags: dict[int, list[VolunteerLabel]] = {}
        if user_ids:
            for user_id, tag_id, name in await self.db.execute(
                select(VolunteerTag.user_id, Tag.id, Tag.name).join(Tag, Tag.id == VolunteerTag.tag_id)
                .where(VolunteerTag.user_id.in_(user_ids)).order_by(Tag.name)
            ):
                tags.setdefault(user_id, []).append(VolunteerLabel(id=tag_id, name=name))
        return [TesterApplicationAdminModel(
            **self._fields(application, titles), user_id=profile.user_id, email=profile.email, phone=profile.phone,
            roles=profile.roles or [], interests=profile.interests or [], tags=tags.get(profile.user_id, []),
        ) for application, profile in rows]

    async def _find(self, user_id: int, innovation_id: str) -> TesterApplication | None:
        return await self.db.scalar(select(TesterApplication).where(
            TesterApplication.user_id == user_id, TesterApplication.innovation_id == innovation_id))

    async def _get(self, application_id: int, *, user_id: int | None = None) -> TesterApplication:
        """:raises NotFoundError: no such application (or not owned by `user_id` when given)."""
        query = select(TesterApplication).where(TesterApplication.id == application_id)
        if user_id is not None:
            query = query.where(TesterApplication.user_id == user_id)
        application = await self.db.scalar(query)
        if application is None:
            raise NotFoundError(resource="TesterApplication", key={"id": application_id}, loc=("path", "application_id"))
        return application

    async def _commit_new(self, application: TesterApplication) -> None:
        """:raises DuplicateError: a concurrent request created the same (user, innovation) application."""
        self.db.add(application)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise DuplicateError(resource="TesterApplication", field="innovation_id", value=application.innovation_id,
                                 loc=("body", "innovation_id")) from None
        await self.db.refresh(application)

    async def apply(self, user: User, data: TesterApplicationCreate) -> TesterApplicationModel:
        """
        :raises ConflictError: the user has no tester profile.
        :raises NotFoundError: unknown innovation.
        :raises DuplicateError: the user already applied to this innovation.
        """
        if await self.db.get(VolunteerProfile, user.id) is None:
            raise ConflictError("Join the tester pool before applying to test an innovation.", loc=("body", "innovation_id"))
        title = await innovation_title(data.innovation_id)
        if await self._find(user.id, data.innovation_id) is not None:
            raise DuplicateError(resource="TesterApplication", field="innovation_id", value=data.innovation_id,
                                 loc=("body", "innovation_id"))
        application = TesterApplication(
            user_id=user.id, innovation_id=data.innovation_id, message=data.message,
            status=ApplicationStatus.pending, source=ApplicationSource.tester,
        )
        await self._commit_new(application)
        return TesterApplicationModel(**self._fields(application, {data.innovation_id: title}))

    async def mine(self, user_id: int) -> list[TesterApplicationModel]:
        applications = list(await self.db.scalars(select(TesterApplication).where(TesterApplication.user_id == user_id)
                                                  .order_by(TesterApplication.created_at.desc(), TesterApplication.id.desc())))
        titles = await innovation_titles({application.innovation_id for application in applications})
        return [TesterApplicationModel(**self._fields(application, titles)) for application in applications]

    async def withdraw(self, user_id: int, application_id: int) -> Delete:
        """:raises NotFoundError: not the user's application.
        :raises ConflictError: the application was already decided."""
        application = await self._get(application_id, user_id=user_id)
        if application.status != ApplicationStatus.pending:
            raise ConflictError("Only pending applications can be withdrawn.", loc=("path", "application_id"))
        await self.db.delete(application)
        await self.db.commit()
        return Delete(deleted=1, detail="Withdrew tester application.")

    async def list_all(self, *, status: ApplicationStatus | None, innovation_id: str | None,
                       limit: int, offset: int) -> ItemList[TesterApplicationAdminModel]:
        filters = []
        if status is not None:
            filters.append(TesterApplication.status == status)
        if innovation_id:
            filters.append(TesterApplication.innovation_id == innovation_id)
        total = await self.db.scalar(select(func.count()).select_from(TesterApplication).where(*filters))
        rows = (await self.db.execute(
            select(TesterApplication, VolunteerProfile)
            .join(VolunteerProfile, VolunteerProfile.user_id == TesterApplication.user_id).where(*filters)
            .order_by(TesterApplication.created_at.desc(), TesterApplication.id.desc()).limit(limit).offset(offset)
        )).tuples().all()
        return ItemList[TesterApplicationAdminModel](total=total, items=await self._admin_models(list(rows)))

    async def _decided(self, application: TesterApplication, status: ApplicationStatus, admin: User,
                       title: str | None = None) -> TesterApplicationAdminModel:
        application.status = status
        application.decided_by, application.decided_at = admin.id, dt.datetime.now(dt.UTC)
        await self.db.commit()
        await self.db.refresh(application)
        profile = await self.db.get(VolunteerProfile, application.user_id)
        titles = {application.innovation_id: title} if title else None
        return (await self._admin_models([(application, profile)], titles))[0]

    async def decide(self, application_id: int, status: ApplicationStatus, admin: User) -> TesterApplicationAdminModel:
        """:raises NotFoundError: no such application."""
        return await self._decided(await self._get(application_id), status, admin)

    async def assign(self, data: TesterApplicationAssign, admin: User) -> TesterApplicationAdminModel:
        """
        Adds a pool tester to an innovation as approved, or upgrades their existing application.
        :raises NotFoundError: the user has no tester profile, or unknown innovation.
        """
        if await self.db.get(VolunteerProfile, data.user_id) is None:
            raise NotFoundError(resource="VolunteerProfile", key={"user_id": data.user_id}, loc=("body", "user_id"))
        title = await innovation_title(data.innovation_id)
        application = await self._find(data.user_id, data.innovation_id)
        if application is None:
            application = TesterApplication(user_id=data.user_id, innovation_id=data.innovation_id,
                                            status=ApplicationStatus.pending, source=ApplicationSource.admin)
            await self._commit_new(application)
        application.source = ApplicationSource.admin
        return await self._decided(application, ApplicationStatus.approved, admin, title)

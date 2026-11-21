from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, DuplicateError, NotFoundError
from app.models import Location, Project, ProjectReview, ProjectStatus, TestSignup, User
from app.repos.project_repo import ProjectRepo, average_rating
from app.schemas.default import Delete, ItemList
from app.schemas.tester import (
    ReviewInput,
    ReviewList,
    ReviewModel,
    TestSignupAdminModel,
    TestSignupCreate,
    TestSignupModel,
)
from app.utils.crud_repo import CRUDRepo


async def _open_project(db: AsyncSession, project_id: int, user: User, action: str) -> Project:
    """The project `user` may sign up for or review: it must be published.
    :raises NotFoundError: missing, or a draft hidden from a non-admin.
    :raises ConflictError: a draft seen by the admin."""
    project = await ProjectRepo(db).get_visible(project_id, include_drafts=user.is_admin)
    if project.status != ProjectStatus.published:
        raise ConflictError(f"Only published projects accept {action}.", loc=("path", "project_id"))
    return project


class TestSignupRepo(CRUDRepo[TestSignup, TestSignupModel]):

    async def get_mine(self, project_id: int, user: User, *, quiet: bool = False) -> TestSignup | None:
        """:raises NotFoundError: `user` has not signed up for the project (unless `quiet`)."""
        signup = await self.db.scalar(
            select(TestSignup).where(TestSignup.project_id == project_id, TestSignup.user_id == user.id)
        )
        if signup is None and not quiet:
            raise NotFoundError(
                resource="TestSignup", key={"project_id": project_id, "user_id": user.id},
                loc=("path", "project_id"),
            )
        return signup

    async def sign_up(self, project_id: int, user: User, data: TestSignupCreate) -> TestSignup:
        """
        Signs `user` up to test a published project.
        :raises NotFoundError: missing or hidden project, unknown location.
        :raises ConflictError: draft project (admin only sees drafts).
        :raises DuplicateError: already signed up.
        """
        await _open_project(self.db, project_id, user, "test sign-ups")
        if data.location_id is not None and await self.db.get(Location, data.location_id) is None:
            raise NotFoundError(resource="Location", key={"id": data.location_id}, loc=("body", "location_id"))
        if await self.get_mine(project_id, user, quiet=True) is not None:
            raise DuplicateError(resource="TestSignup", field="project_id", value=project_id, loc=("path", "project_id"))
        signup = await self.create(data, project_id=project_id, user_id=user.id)
        await self.db.refresh(signup)  # loads the server-side created_at
        return signup

    async def withdraw(self, project_id: int, user: User) -> Delete:
        """Removes the user's own sign-up, whatever the project status.
        :raises NotFoundError: not signed up."""
        await self.db.delete(await self.get_mine(project_id, user))
        await self.db.commit()
        return Delete(deleted=1, detail="Deleted TestSignup.")

    async def list_for_project(self, project_id: int, *, limit: int | None, offset: int) -> ItemList[TestSignupAdminModel]:
        """Sign-ups with the testers' contact details, newest first (admin; drafts included).
        :raises NotFoundError: missing project."""
        await ProjectRepo(self.db).get_one(id=project_id, key_loc="path")
        total = await self.db.scalar(
            select(func.count()).select_from(TestSignup).where(TestSignup.project_id == project_id)
        )
        rows = (await self.db.execute(
            select(TestSignup, User.username, User.email)
            .join(User, TestSignup.user_id == User.id)
            .where(TestSignup.project_id == project_id)
            .order_by(TestSignup.id.desc())
            .offset(offset).limit(limit)
        )).all()
        return ItemList[TestSignupAdminModel](total=total, items=[
            TestSignupAdminModel(**TestSignupModel.model_validate(signup).model_dump(), username=username, email=email)
            for signup, username, email in rows
        ])


class ReviewRepo(CRUDRepo[ProjectReview, ReviewModel]):

    @staticmethod
    def _model(review: ProjectReview, username: str) -> ReviewModel:
        return ReviewModel(
            id=review.id, project_id=review.project_id, user_id=review.user_id, username=username,
            rating=review.rating, comment=review.comment,
            created_at=review.created_at, updated_at=review.updated_at,
        )

    async def get_mine(self, project_id: int, user: User) -> ReviewModel:
        """:raises NotFoundError: `user` has not reviewed the project."""
        review = await self._find(project_id, user)
        if review is None:
            raise NotFoundError(
                resource="ProjectReview", key={"project_id": project_id, "user_id": user.id},
                loc=("path", "project_id"),
            )
        return self._model(review, user.username)

    async def _find(self, project_id: int, user: User) -> ProjectReview | None:
        return await self.db.scalar(
            select(ProjectReview).where(ProjectReview.project_id == project_id, ProjectReview.user_id == user.id)
        )

    async def put_mine(self, project_id: int, user: User, data: ReviewInput) -> tuple[ReviewModel, bool]:
        """
        Creates or replaces the user's review of a published project.
        Returns the review and whether it was created.
        :raises NotFoundError: missing or hidden project.
        :raises ConflictError: draft project (admin only sees drafts).
        """
        await _open_project(self.db, project_id, user, "reviews")
        review = await self._find(project_id, user)
        created = review is None
        if created:
            review = ProjectReview(project_id=project_id, user_id=user.id, **data.model_dump())
            self.db.add(review)
        else:
            review.rating, review.comment = data.rating, data.comment
        await self.db.commit()
        await self.db.refresh(review)  # loads the server-side timestamps
        return self._model(review, user.username), created

    async def list_for_project(self, project_id: int, user: User | None, *, limit: int | None, offset: int) -> ReviewList:
        """Reviews of a visible project with the average rating, newest first.
        :raises NotFoundError: missing, or a draft hidden from a non-admin."""
        await ProjectRepo(self.db).get_visible(project_id, include_drafts=user is not None and user.is_admin)
        total = await self.db.scalar(
            select(func.count()).select_from(ProjectReview).where(ProjectReview.project_id == project_id)
        )
        rows = (await self.db.execute(
            select(ProjectReview, User.username)
            .join(User, ProjectReview.user_id == User.id)
            .where(ProjectReview.project_id == project_id)
            .order_by(ProjectReview.id.desc())
            .offset(offset).limit(limit)
        )).all()
        return ReviewList(
            total=total,
            items=[self._model(review, username) for review, username in rows],
            rating_avg=await average_rating(self.db, project_id),
        )

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy import select

from app.models import ApplicationStatus, Tag, User
from app.repos.tester_application_repo import TesterApplicationRepo
from app.repos.volunteer_repo import VolunteerRepo
from app.schemas.tester_application import (
    TesterApplicationAdminModel,
    TesterApplicationAssign,
    TesterApplicationCreate,
    TesterApplicationDecision,
    TesterApplicationModel,
)
from app.modules.knowledge import Category
from app.modules.tester_tags import INTEREST_LABELS, ROLE_LABELS, TesterRole
from app.schemas.volunteer import VolunteerInput, VolunteerLabel, VolunteerModel, VolunteerOption, VolunteerOptions

from app.dependencies import DatabaseDep, PaginationDep
from app.docs import Tags
from app.exceptions import ForbiddenError
from app.repos.tester_repo import ReviewRepo, TestSignupRepo
from app.schemas.default import CONFLICT, Delete, ItemList, NOT_FOUND
from app.schemas.tester import (
    ReviewInput,
    ReviewList,
    ReviewModel,
    TestSignupAdminModel,
    TestSignupCreate,
    TestSignupModel,
)
from app.utils.auth import CurrentAdminDep, CurrentUserDep, OptionalUserDep, get_current_admin

router = APIRouter(
    tags=[Tags.Tester],
    responses={},
)


# ============ test sign-ups ============


@router.post("/projects/{project_id}/test-signups",
             dependencies=None,
             response_model=TestSignupModel,
             responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
             status_code=status.HTTP_201_CREATED,
             summary="Sign up to test project",
             response_description="Successful Response")
async def create_test_signup(
        db: DatabaseDep,
        user: CurrentUserDep,
        signup: TestSignupCreate,
        project_id: int = Path(ge=1),
):
    """
    Declare willingness to test a published project, optionally with where you come from and a message. \\
    Raises 401 Unauthorized when not logged in, 404 Not Found for a missing or unpublished project
    or an unknown location, 409 Conflict when already signed up.
    """
    return await TestSignupRepo(db).sign_up(project_id, user, signup)


@router.get("/projects/{project_id}/test-signups/mine",
            dependencies=None,
            response_model=TestSignupModel,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get my test sign-up",
            response_description="Successful Response")
async def get_my_test_signup(
        db: DatabaseDep,
        user: CurrentUserDep,
        project_id: int = Path(ge=1),
):
    """
    Get the logged-in user's sign-up for a project. \\
    Raises 401 Unauthorized when not logged in, 404 Not Found when not signed up.
    """
    return await TestSignupRepo(db).get_mine(project_id, user)


@router.delete("/projects/{project_id}/test-signups/mine",
               dependencies=None,
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
               status_code=status.HTTP_200_OK,
               summary="Withdraw my test sign-up",
               response_description="Successful Response")
async def delete_my_test_signup(
        db: DatabaseDep,
        user: CurrentUserDep,
        project_id: int = Path(ge=1),
):
    """
    Withdraw the logged-in user's sign-up. \\
    Raises 401 Unauthorized when not logged in, 404 Not Found when not signed up.
    """
    return await TestSignupRepo(db).withdraw(project_id, user)


@router.get("/projects/{project_id}/test-signups",
            dependencies=[Depends(get_current_admin)],
            response_model=ItemList[TestSignupAdminModel],
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get project test sign-ups",
            response_description="Successful Response")
async def get_test_signups(
        db: DatabaseDep,
        page: PaginationDep,
        project_id: int = Path(ge=1),
):
    """
    Get the project's sign-ups with the testers' username and email for contact, newest first. Admin only. \\
    Paginated with `?limit=&offset=`. Raises 404 Not Found when the project does not exist.
    """
    return await TestSignupRepo(db).list_for_project(project_id, limit=page.limit, offset=page.offset)


# ============ reviews ============


@router.get("/projects/{project_id}/reviews",
            dependencies=None,
            response_model=ReviewList,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get project reviews",
            response_description="Successful Response")
async def get_reviews(
        db: DatabaseDep,
        user: OptionalUserDep,
        page: PaginationDep,
        project_id: int = Path(ge=1),
):
    """
    Get the project's reviews, newest first, with `rating_avg` (null without reviews). Public. \\
    Paginated with `?limit=&offset=` (`total` is the number of reviews). \\
    Raises 404 Not Found when the project does not exist, or is a draft and the caller is not an admin.
    """
    return await ReviewRepo(db).list_for_project(project_id, user, limit=page.limit, offset=page.offset)


@router.get("/projects/{project_id}/reviews/mine",
            dependencies=None,
            response_model=ReviewModel,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get my review",
            response_description="Successful Response")
async def get_my_review(
        db: DatabaseDep,
        user: CurrentUserDep,
        project_id: int = Path(ge=1),
):
    """
    Get the logged-in user's review of a project. \\
    Raises 401 Unauthorized when not logged in, 404 Not Found when not reviewed.
    """
    return await ReviewRepo(db).get_mine(project_id, user)


@router.put("/projects/{project_id}/reviews/mine",
            dependencies=None,
            response_model=ReviewModel,
            responses={
                status.HTTP_201_CREATED: {"model": ReviewModel, "description": "Review created"},
                status.HTTP_404_NOT_FOUND: NOT_FOUND,
                status.HTTP_409_CONFLICT: CONFLICT,
            },
            status_code=status.HTTP_200_OK,
            summary="Create or update my review",
            response_description="Review updated")
async def put_my_review(
        db: DatabaseDep,
        user: CurrentUserDep,
        review: ReviewInput,
        response: Response,
        project_id: int = Path(ge=1),
):
    """
    Create (201) or replace (200) the logged-in user's review of a published project:
    `rating` 1-5 and an optional `comment` (feedback or proposed improvements; omitted or null clears it). \\
    Raises 401 Unauthorized when not logged in, 404 Not Found for a missing or unpublished project,
    422 for a rating outside 1-5.
    """
    result, created = await ReviewRepo(db).put_mine(project_id, user, review)
    if created:
        response.status_code = status.HTTP_201_CREATED
    return result


@router.delete("/reviews/{review_id}",
               dependencies=[Depends(get_current_admin)],
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
               status_code=status.HTTP_200_OK,
               summary="Delete review",
               response_description="Successful Response")
async def delete_review(
        db: DatabaseDep,
        review_id: int = Path(ge=1),
):
    """
    Delete a review (moderation). Admin only. \\
    Raises 404 Not Found when it does not exist.
    """
    return await ReviewRepo(db).delete_one(id=review_id, key_loc="path")


# ============ project-independent volunteer pool ============


@router.get("/volunteers/mine", response_model=VolunteerModel | None)
async def get_my_volunteer_profile(db: DatabaseDep, user: CurrentUserDep):
    return await VolunteerRepo(db).mine(user.id)


def ensure_not_admin(user: User) -> None:
    """:raises ForbiddenError: Administrators cannot join the tester pool or apply as testers."""
    if user.is_admin:
        raise ForbiddenError(msg="Administrators cannot register as testers.", loc=("header", "authorization"))


@router.put("/volunteers/mine", response_model=VolunteerModel)
async def put_my_volunteer_profile(db: DatabaseDep, user: CurrentUserDep, data: VolunteerInput):
    """Create or replace own profile; tagging failure does not block registration.

    Raises 403 Forbidden for administrators.
    """
    ensure_not_admin(user)
    return await VolunteerRepo(db).put_mine(user.id, data)


@router.delete("/volunteers/mine", response_model=Delete)
async def withdraw_volunteer_profile(db: DatabaseDep, user: CurrentUserDep):
    """Delete own profile and tags; retain the login account."""
    return await VolunteerRepo(db).withdraw(user.id)


@router.get("/volunteers/options", response_model=VolunteerOptions)
async def get_volunteer_options(user: CurrentUserDep):
    """Fixed lists for the explicit tester tags: who the tester is and what they can test."""
    return VolunteerOptions(
        roles=[VolunteerOption(id=role, label=label) for role, label in ROLE_LABELS.items()],
        interests=[VolunteerOption(id=category, label=label) for category, label in INTEREST_LABELS.items()],
    )


@router.get("/volunteers/tags", dependencies=[Depends(get_current_admin)], response_model=list[VolunteerLabel])
async def get_volunteer_tags(db: DatabaseDep):
    return [VolunteerLabel(id=t.id, name=t.name) for t in await db.scalars(select(Tag).order_by(Tag.name))]


@router.get("/volunteers", dependencies=[Depends(get_current_admin)], response_model=ItemList[VolunteerModel])
async def get_volunteer_pool(
    db: DatabaseDep, page: PaginationDep,
    q: str = Query(default="", max_length=200), tag_id: int | None = Query(default=None, ge=1),
    role: TesterRole | None = Query(default=None), interest: Category | None = Query(default=None),
):
    """Private administrator pool: description search, topic, role and interest filters, newest first."""
    return await VolunteerRepo(db).list_pool(query=q.strip(), tag_id=tag_id, role=role, interest=interest,
                                             limit=page.limit, offset=page.offset)


# ============ tester applications to knowledge innovations ============


@router.post("/tester-applications",
             response_model=TesterApplicationModel,
             responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
             status_code=status.HTTP_201_CREATED,
             summary="Apply to test an innovation")
async def apply_as_tester(db: DatabaseDep, user: CurrentUserDep, data: TesterApplicationCreate):
    """
    Apply to test a knowledge-base innovation; the application starts as `pending`. \\
    Raises 403 for administrators, 409 Conflict without a tester profile or on a duplicate application,
    404 Not Found for an unknown innovation, 503 when the knowledge base is unavailable.
    """
    ensure_not_admin(user)
    return await TesterApplicationRepo(db).apply(user, data)


@router.get("/tester-applications/mine", response_model=list[TesterApplicationModel], summary="Get own applications")
async def get_my_tester_applications(db: DatabaseDep, user: CurrentUserDep):
    """Own applications with innovation titles (slug when the innovation is gone), newest first."""
    return await TesterApplicationRepo(db).mine(user.id)


@router.delete("/tester-applications/mine/{application_id}",
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
               summary="Withdraw own pending application")
async def withdraw_tester_application(db: DatabaseDep, user: CurrentUserDep, application_id: int = Path(ge=1)):
    """Withdraw (delete) an own application. Raises 404 when not owned, 409 Conflict once decided."""
    return await TesterApplicationRepo(db).withdraw(user.id, application_id)


@router.get("/tester-applications",
            dependencies=[Depends(get_current_admin)],
            response_model=ItemList[TesterApplicationAdminModel],
            summary="Get tester applications")
async def get_tester_applications(
    db: DatabaseDep, page: PaginationDep,
    status_: ApplicationStatus | None = Query(default=None, alias="status"),
    innovation_id: str | None = Query(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120),
):
    """Admin only. Paginated applications, newest first, with tester contact and tags; filters `status`, `innovation_id`."""
    return await TesterApplicationRepo(db).list_all(status=status_, innovation_id=innovation_id,
                                                    limit=page.limit, offset=page.offset)


@router.patch("/tester-applications/{application_id}",
              response_model=TesterApplicationAdminModel,
              responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
              summary="Approve or reject an application")
async def decide_tester_application(db: DatabaseDep, admin: CurrentAdminDep, data: TesterApplicationDecision,
                                    application_id: int = Path(ge=1)):
    """Admin only. Sets `approved` or `rejected` and records the deciding admin and time."""
    return await TesterApplicationRepo(db).decide(application_id, ApplicationStatus(data.status), admin)


@router.post("/tester-applications/assign",
             response_model=TesterApplicationAdminModel,
             responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
             summary="Add a tester to an innovation")
async def assign_tester(db: DatabaseDep, admin: CurrentAdminDep, data: TesterApplicationAssign):
    """
    Admin only. Adds a pool tester to an innovation as `approved` with `source=admin`,
    or upgrades their existing application. Raises 404 for an unknown tester profile or innovation.
    """
    return await TesterApplicationRepo(db).assign(data, admin)

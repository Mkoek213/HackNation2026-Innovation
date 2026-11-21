from fastapi import APIRouter, Path, Query, status

from app.dependencies import DatabaseDep, PaginationDep
from app.docs import Tags
from app.exceptions import ForbiddenError
from app.models import IdeaStage, IdeaStatus
from app.repos.idea_repo import IdeaRepo
from app.schemas.default import ItemList, Delete, NOT_FOUND, CONFLICT
from app.schemas.idea import IdeaCreate, IdeaModel, IdeaUpdate
from app.utils.auth import CurrentUserDep, OptionalUserDep

router = APIRouter(
    prefix="/ideas",
    tags=[Tags.Ideas],
    responses={},
)


@router.get("",
            dependencies=None,
            response_model=ItemList[IdeaModel],
            status_code=status.HTTP_200_OK,
            summary="Get ideas",
            response_description="Successful Response")
async def get_ideas(
        db: DatabaseDep,
        page: PaginationDep,
        user: OptionalUserDep,
        tag_id: int | None = Query(None, ge=1, description="Only ideas with this tag."),
        stage: IdeaStage | None = Query(None, description="Only ideas at this stage."),
        idea_status: IdeaStatus = Query(
            IdeaStatus.published, alias="status",
            description="Public: only `published`. The admin can list `submitted` ideas for review, or `rejected` ones.",
        ),
):
    """
    Get ideas, newest first. Public for published ideas. \\
    Paginated with `?limit=&offset=` (`total` is the unpaginated count). \\
    Raises 403 Forbidden when a non-admin asks for another status than `published`.
    """
    if idea_status != IdeaStatus.published and (user is None or not user.is_admin):
        raise ForbiddenError(msg="Only the admin can list unpublished ideas.", loc=("query", "status"))
    return await IdeaRepo(db).search(
        status=idea_status, tag_id=tag_id, stage=stage, limit=page.limit, offset=page.offset,
    )


@router.get("/mine",
            dependencies=None,
            response_model=ItemList[IdeaModel],
            status_code=status.HTTP_200_OK,
            summary="Get my ideas",
            response_description="Successful Response")
async def get_my_ideas(
        db: DatabaseDep,
        page: PaginationDep,
        user: CurrentUserDep,
        idea_status: IdeaStatus | None = Query(None, alias="status", description="Only ideas with this status."),
):
    """
    Get the logged-in user's own ideas in every status, newest first. \\
    Paginated with `?limit=&offset=`. Raises 401 Unauthorized when not logged in.
    """
    return await IdeaRepo(db).search(
        author_id=user.id, status=idea_status, limit=page.limit, offset=page.offset,
    )


@router.get("/{idea_id}",
            dependencies=None,
            response_model=IdeaModel,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get idea one",
            response_description="Successful Response")
async def get_idea_one(
        db: DatabaseDep,
        user: OptionalUserDep,
        idea_id: int = Path(ge=1),
):
    """
    Get one idea. Public when published; otherwise only its author and the admin see it. \\
    Raises 404 Not Found when it does not exist or is not visible.
    """
    return await IdeaRepo(db).get_visible(idea_id, user)


@router.post("",
             dependencies=None,
             response_model=IdeaModel,
             status_code=status.HTTP_201_CREATED,
             summary="Create idea",
             response_description="Successful Response")
async def create_idea(
        db: DatabaseDep,
        user: CurrentUserDep,
        idea: IdeaCreate,
):
    """
    Submit an idea (status `submitted`) as the logged-in user. \\
    Raises 401 Unauthorized when not logged in, 422 when `tag_id` or `location_id` does not exist.
    """
    return await IdeaRepo(db).create_idea(user, idea)


@router.patch("/{idea_id}",
              dependencies=None,
              response_model=IdeaModel,
              responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
              status_code=status.HTTP_200_OK,
              summary="Update idea",
              response_description="Successful Response")
async def update_idea(
        db: DatabaseDep,
        user: CurrentUserDep,
        idea: IdeaUpdate,
        idea_id: int = Path(ge=1),
):
    """
    Update an idea. The author edits `title`, `essence`, `target_group`, `stage`, `tag_id`, `location_id`
    while the idea is `submitted`; the admin edits any field and sets `status` (`published` / `rejected`). \\
    Raises 404 Not Found when it does not exist, 403 Forbidden for someone else's idea or a non-admin `status`,
    409 Conflict when the author edits an idea that is no longer `submitted`.
    """
    return await IdeaRepo(db).update_idea(idea_id, idea, user)


@router.delete("/{idea_id}",
               dependencies=None,
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
               status_code=status.HTTP_200_OK,
               summary="Delete idea",
               response_description="Successful Response")
async def delete_idea(
        db: DatabaseDep,
        user: CurrentUserDep,
        idea_id: int = Path(ge=1),
):
    """
    Delete an idea. Its author or the admin. \\
    Raises 404 Not Found when it does not exist, 403 Forbidden for someone else's idea.
    """
    return await IdeaRepo(db).delete_idea(idea_id, user)

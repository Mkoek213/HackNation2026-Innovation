from fastapi import APIRouter, Depends, status, Path

from app.dependencies import DatabaseDep, PaginationDep
from app.docs import Tags
from app.exceptions import ConflictError
from app.models import UserRole
from app.repos.user_repo import UserRepo
from app.schemas.default import ItemList, Delete, NOT_FOUND, CONFLICT
from app.schemas.user import UserModel, UserCreate, UserUpdate
from app.utils.auth import get_current_admin, CurrentUserDep, CurrentAdminDep

router = APIRouter(
    prefix="/users",
    tags=[Tags.Users],
    responses={},
)


@router.get("/me",
            dependencies=None,
            response_model=UserModel,
            status_code=status.HTTP_200_OK,
            summary="Get current user",
            response_description="Successful Response")
async def get_me(user: CurrentUserDep):
    """
    Get the logged-in user. \\
    Raises 401 Unauthorized when not logged in.
    """
    return user


@router.patch("/me",
              dependencies=None,
              response_model=UserModel,
              responses={status.HTTP_409_CONFLICT: CONFLICT},
              status_code=status.HTTP_200_OK,
              summary="Update my profile",
              response_description="Successful Response")
async def patch_me(db: DatabaseDep, user: CurrentUserDep, data: UserUpdate):
    """
    Update the logged-in user's own username, e-mail or password. \\
    Non-admins cannot change `role`. Raises 401 when not logged in, 409 on duplicates.
    """
    payload = data.model_dump_null()
    if not user.is_admin:
        payload.pop("role", None)
    if not payload:
        return user
    return await UserRepo(db).update_user(UserUpdate.model_validate(payload), id=user.id)


@router.get("",
            dependencies=[Depends(get_current_admin)],
            response_model=ItemList[UserModel],
            status_code=status.HTTP_200_OK,
            summary="Get users",
            response_description="Successful Response")
async def get_users(db: DatabaseDep, page: PaginationDep):
    """
    Get users, paginated with `?limit=&offset=` (`total` is the unpaginated count). Admin only.
    """
    return await UserRepo(db).get_all(limit=page.limit, offset=page.offset)


@router.get("/{user_id}",
            dependencies=[Depends(get_current_admin)],
            response_model=UserModel,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get user one",
            response_description="Successful Response")
async def get_user_one(
        db: DatabaseDep,
        user_id: int = Path(ge=1),
):
    """
    Get user. Admin only. \\
    Checks if user exists, otherwise raises 404 Not Found.
    """
    return await UserRepo(db).get_one(id=user_id, key_loc="path")


@router.post("",
             dependencies=[Depends(get_current_admin)],
             response_model=UserModel,
             responses={status.HTTP_409_CONFLICT: CONFLICT},
             status_code=status.HTTP_201_CREATED,
             summary="Create user",
             response_description="Successful Response")
async def create_user(
        db: DatabaseDep,
        user: UserCreate,
):
    """
    Create user. Admin only. \\
    Raises 409 Conflict when the username is already taken.
    """
    return await UserRepo(db).create_user(user)


@router.patch("/{user_id}",
              dependencies=None,
              response_model=UserModel,
              responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
              status_code=status.HTTP_200_OK,
              summary="Update user",
              response_description="Successful Response")
async def update_user(
        db: DatabaseDep,
        admin: CurrentAdminDep,
        user: UserUpdate,
        user_id: int = Path(ge=1),
):
    """
    Update user (username, password, role). Admin only. \\
    Checks if user exists, otherwise raises 404 Not Found. \\
    Raises 409 Conflict when the username is taken, or when an admin tries to remove their own admin role.
    """
    if user_id == admin.id and user.role is not None and user.role != UserRole.admin:
        raise ConflictError("You cannot remove your own admin role.", loc=("body", "role"))
    return await UserRepo(db).update_user(user, id=user_id)


@router.delete("/{user_id}",
               dependencies=None,
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
               status_code=status.HTTP_200_OK,
               summary="Delete one user",
               response_description="Successful Response")
async def delete_user_one(
        db: DatabaseDep,
        admin: CurrentAdminDep,
        user_id: int = Path(ge=1),
):
    """
    Delete user. Admin only. \\
    Checks if user exists, otherwise raises 404 Not Found. \\
    Raises 409 Conflict when an admin tries to delete their own account.
    """
    if user_id == admin.id:
        raise ConflictError("You cannot delete your own account.", loc=("path", "user_id"))
    return await UserRepo(db).delete_one(id=user_id, key_loc="path")

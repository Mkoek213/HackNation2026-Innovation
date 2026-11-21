from fastapi import APIRouter, Depends, status, Path

from app.dependencies import DatabaseDep
from app.docs import Tags
from app.repos.tag_repo import SubtagRepo, TagRepo
from app.schemas.default import ItemList, Delete, NOT_FOUND, CONFLICT
from app.schemas.tag import (
    SubtagCreate,
    SubtagModel,
    SubtagUpdate,
    TagCreate,
    TagModel,
    TagUpdate,
    TagWithSubtags,
)
from app.utils.auth import get_current_admin

router = APIRouter(
    tags=[Tags.Tags],
    responses={},
)


@router.get("/tags",
            dependencies=None,
            response_model=ItemList[TagWithSubtags],
            status_code=status.HTTP_200_OK,
            summary="Get tags with subtags",
            response_description="Successful Response")
async def get_tags(db: DatabaseDep):
    """
    Get all tags ordered by name, each with its nested subtags. Public. \\
    Not paginated: the admin-managed dictionary is small and pickers need all of it.
    """
    tags = await TagRepo(db).get_all_nested()
    return ItemList[TagWithSubtags](total=len(tags), items=[*tags])


@router.post("/tags",
             dependencies=[Depends(get_current_admin)],
             response_model=TagModel,
             responses={status.HTTP_409_CONFLICT: CONFLICT},
             status_code=status.HTTP_201_CREATED,
             summary="Create tag",
             response_description="Successful Response")
async def create_tag(
        db: DatabaseDep,
        tag: TagCreate,
):
    """
    Create tag. Admin only. \\
    Raises 409 Conflict when the name is already taken.
    """
    return await TagRepo(db).create_tag(tag)


@router.patch("/tags/{tag_id}",
              dependencies=[Depends(get_current_admin)],
              response_model=TagModel,
              responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
              status_code=status.HTTP_200_OK,
              summary="Update tag",
              response_description="Successful Response")
async def update_tag(
        db: DatabaseDep,
        tag: TagUpdate,
        tag_id: int = Path(ge=1),
):
    """
    Update tag (name, description). Admin only. \\
    Checks if tag exists, otherwise raises 404 Not Found. \\
    Raises 409 Conflict when the name is already taken.
    """
    return await TagRepo(db).update_tag(tag, id=tag_id)


@router.delete("/tags/{tag_id}",
               dependencies=[Depends(get_current_admin)],
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
               status_code=status.HTTP_200_OK,
               summary="Delete tag",
               response_description="Successful Response")
async def delete_tag(
        db: DatabaseDep,
        tag_id: int = Path(ge=1),
):
    """
    Delete tag. Admin only. \\
    Checks if tag exists, otherwise raises 404 Not Found. \\
    Raises 409 Conflict while the tag still has subtags or is used.
    """
    return await TagRepo(db).delete_one(id=tag_id, key_loc="path")


@router.post("/tags/{tag_id}/subtags",
             dependencies=[Depends(get_current_admin)],
             response_model=SubtagModel,
             responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
             status_code=status.HTTP_201_CREATED,
             summary="Create subtag",
             response_description="Successful Response")
async def create_subtag(
        db: DatabaseDep,
        subtag: SubtagCreate,
        tag_id: int = Path(ge=1),
):
    """
    Create subtag under a tag. Admin only. \\
    Checks if tag exists, otherwise raises 404 Not Found. \\
    Raises 409 Conflict when the tag already has a subtag with this name.
    """
    return await SubtagRepo(db).create_subtag(tag_id, subtag)


@router.patch("/subtags/{subtag_id}",
              dependencies=[Depends(get_current_admin)],
              response_model=SubtagModel,
              responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
              status_code=status.HTTP_200_OK,
              summary="Update subtag",
              response_description="Successful Response")
async def update_subtag(
        db: DatabaseDep,
        subtag: SubtagUpdate,
        subtag_id: int = Path(ge=1),
):
    """
    Update subtag (name, description). Admin only. \\
    Checks if subtag exists, otherwise raises 404 Not Found. \\
    Raises 409 Conflict when its tag already has a subtag with this name.
    """
    return await SubtagRepo(db).update_subtag(subtag, id=subtag_id)


@router.delete("/subtags/{subtag_id}",
               dependencies=[Depends(get_current_admin)],
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
               status_code=status.HTTP_200_OK,
               summary="Delete subtag",
               response_description="Successful Response")
async def delete_subtag(
        db: DatabaseDep,
        subtag_id: int = Path(ge=1),
):
    """
    Delete subtag. Admin only. \\
    Checks if subtag exists, otherwise raises 404 Not Found. \\
    Raises 409 Conflict while the subtag is used.
    """
    return await SubtagRepo(db).delete_one(id=subtag_id, key_loc="path")

import logging
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.config import settings
from app.dependencies import DatabaseDep, PaginationDep
from app.docs import Tags
from app.exceptions import NotFoundError
from app.models import ProjectDocument, ProjectStatus
from app.repos.conversation_repo import ProjectMatchRepo
from app.repos.project_repo import ParticipantsLevel, ProjectDocumentRepo, ProjectParticipantRepo, ProjectRepo
from app.schemas.default import CONFLICT, Delete, ErrorResponse, ItemList, NOT_FOUND
from app.schemas.conversation import ProjectMatchModel
from app.schemas.geojson import FeatureCollection
from app.schemas.tag import Name
from app.schemas.project import (
    ParticipantInput,
    ParticipantProperties,
    ParticipantsSummary,
    ProjectCreate,
    ProjectDetail,
    ProjectDocumentModel,
    ProjectModel,
    ProjectProperties,
    ProjectUpdate,
)
from app.services.files import FileStorageDep
from app.services.rag import get_vector_store
from app.utils.auth import OptionalUserDep, VisitorDep, get_current_admin

router = APIRouter(
    prefix="/projects",
    tags=[Tags.Projects],
    responses={},
)

logger = logging.getLogger(__name__)

PAYLOAD_TOO_LARGE = {"model": ErrorResponse, "description": "File too large"}
LevelQuery = Annotated[ParticipantsLevel, Query(description="`county` sums municipalities into their county (powiat).")]


# ============ vector DB hooks ============
# Called after the database commit. A vector store failure is logged and does not fail the
# admin's request (the database is the source of truth); saving the project again retries.

async def index_project(db: DatabaseDep, project_id: int) -> None:
    """A published project changed (published, edited, PDF added or removed): send it to the vector DB."""
    project = await ProjectRepo(db).get_one(id=project_id)
    documents = (await db.scalars(
        select(ProjectDocument).where(ProjectDocument.project_id == project_id).order_by(ProjectDocument.id)
    )).all()
    try:
        await get_vector_store(db).upsert_project(project, documents)
    except Exception as exc:
        logger.warning("Vector store failed to index project %s: %s", project_id, type(exc).__name__)


async def unindex_project(db: DatabaseDep, project_id: int) -> None:
    """A project was unpublished or deleted: remove it from the vector DB."""
    try:
        await get_vector_store(db).delete_project(project_id)
    except Exception as exc:
        logger.warning("Vector store failed to remove project %s: %s", project_id, type(exc).__name__)


# ============ projects ============


@router.get("",
            dependencies=None,
            response_model=ItemList[ProjectModel],
            status_code=status.HTTP_200_OK,
            summary="Get projects",
            response_description="Successful Response")
async def get_projects(
        db: DatabaseDep,
        user: OptionalUserDep,
        page: PaginationDep,
        tag_id: int | None = Query(None, ge=1, description="Only projects with this main tag."),
        subtag_id: int | None = Query(None, ge=1, description="Only projects with this subtag."),
        location_id: int | None = Query(None, ge=1, description="Only projects in this location or the units inside it."),
        q: str | None = Query(None, min_length=1, max_length=100, description="Title or summary fragment."),
        project_status: ProjectStatus | None = Query(None, alias="status", description="Admin only; others always get published projects."),
):
    """
    Get projects, newest first, without the full description. Public. \\
    Non-admins get published projects only; an admin gets drafts too and can filter by `status`. \\
    Paginated with `?limit=&offset=` (`total` is the unpaginated count).
    """
    return await ProjectRepo(db).search(
        include_drafts=user is not None and user.is_admin, status=project_status,
        tag_id=tag_id, subtag_id=subtag_id, location_id=location_id, q=q,
        limit=page.limit, offset=page.offset,
    )


@router.get("/geojson",
            dependencies=None,
            response_model=FeatureCollection[ProjectProperties],
            status_code=status.HTTP_200_OK,
            summary="Get projects as GeoJSON",
            response_description="GeoJSON FeatureCollection")
async def get_projects_geojson(
        db: DatabaseDep,
        tag_id: int | None = Query(None, ge=1, description="Only projects with this main tag."),
        subtag_id: int | None = Query(None, ge=1, description="Only projects with this subtag."),
):
    """
    Get published projects as GeoJSON `Point` features for Leaflet `L.geoJSON(data)` or a MapLibre source. Public. \\
    The point is the project's own coordinates, or its location's centroid; projects with neither are left out.
    `properties` are `{id, title, tag_id, subtag_id}`. Not paginated.
    """
    return await ProjectRepo(db).geojson(tag_id=tag_id, subtag_id=subtag_id)


@router.get("/{project_id}",
            dependencies=None,
            response_model=ProjectDetail,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get project one",
            response_description="Successful Response")
async def get_project_one(
        db: DatabaseDep,
        user: OptionalUserDep,
        project_id: int = Path(ge=1),
):
    """
    Get one project with its description, PDFs and participants total. Public. \\
    Raises 404 Not Found when it does not exist, or is a draft and the caller is not an admin.
    """
    repo = ProjectRepo(db)
    project = await repo.get_visible(project_id, include_drafts=user is not None and user.is_admin)
    return await repo.detail(project)


@router.post("",
             dependencies=[Depends(get_current_admin)],
             response_model=ProjectDetail,
             responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
             status_code=status.HTTP_201_CREATED,
             summary="Create project",
             response_description="Successful Response")
async def create_project(
        db: DatabaseDep,
        project: ProjectCreate,
):
    """
    Create a project as a `draft`. Admin only. \\
    Raises 404 Not Found for an unknown tag, subtag or location, and 422 when the subtag
    belongs to another tag or only one of latitude/longitude is given.
    """
    repo = ProjectRepo(db)
    return await repo.detail(await repo.create_project(project))


@router.patch("/{project_id}",
              dependencies=[Depends(get_current_admin)],
              response_model=ProjectDetail,
              responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
              status_code=status.HTTP_200_OK,
              summary="Update project",
              response_description="Successful Response")
async def update_project(
        db: DatabaseDep,
        changes: ProjectUpdate,
        project_id: int = Path(ge=1),
):
    """
    Update a project. `{"status": "published"}` publishes it (and sends it to the vector DB),
    `{"status": "draft"}` hides it again. Admin only. \\
    Raises 404 Not Found when it does not exist, or for an unknown tag, subtag or location;
    422 as in create.
    """
    repo = ProjectRepo(db)
    was_published = (await repo.get_one(id=project_id, key_loc="path")).status == ProjectStatus.published
    project = await repo.update_project(changes, id=project_id)
    if project.status == ProjectStatus.published:
        await index_project(db, project.id)
    elif was_published:
        await unindex_project(db, project.id)
    return await repo.detail(project)


@router.delete("/{project_id}",
               dependencies=[Depends(get_current_admin)],
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_409_CONFLICT: CONFLICT},
               status_code=status.HTTP_200_OK,
               summary="Delete project",
               response_description="Successful Response")
async def delete_project(
        db: DatabaseDep,
        storage: FileStorageDep,
        project_id: int = Path(ge=1),
):
    """
    Delete a project with its PDFs and participant data. Admin only. \\
    Raises 404 Not Found when it does not exist.
    """
    await ProjectRepo(db).delete_project(project_id, storage)
    await unindex_project(db, project_id)
    return Delete(deleted=1, detail="Deleted Project.")


# ============ documents (PDFs) ============


@router.post("/{project_id}/documents",
             dependencies=[Depends(get_current_admin)],
             response_model=ProjectDocumentModel,
             responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_413_CONTENT_TOO_LARGE: PAYLOAD_TOO_LARGE},
             status_code=status.HTTP_201_CREATED,
             summary="Upload project PDF",
             response_description="Successful Response")
async def upload_project_document(
        db: DatabaseDep,
        storage: FileStorageDep,
        title: Annotated[Name, Form(min_length=1, max_length=200, description="Accessible link text.")],
        file: Annotated[UploadFile, File(description="PDF file (application/pdf).")],
        project_id: int = Path(ge=1),
):
    """
    Upload a PDF to a project (multipart form: `title`, `file`). Admin only. \\
    Raises 404 Not Found when the project does not exist, 422 when the file is not a PDF,
    413 when it is larger than `MAX_UPLOAD_BYTES` (default 20 MB).
    """
    document = await ProjectDocumentRepo(db).upload(
        project_id, title, file.file, file.content_type, file.size, storage,
        max_bytes=settings.max_upload_bytes,
    )
    project = await ProjectRepo(db).get_one(id=project_id)
    if project.status == ProjectStatus.published:
        await index_project(db, project_id)
    return document


@router.get("/{project_id}/documents/{document_id}",
            dependencies=None,
            response_class=StreamingResponse,
            responses={
                status.HTTP_200_OK: {"content": {"application/pdf": {}}, "description": "The PDF"},
                status.HTTP_404_NOT_FOUND: NOT_FOUND,
            },
            summary="Get project PDF",
            response_description="The PDF")
async def get_project_document(
        db: DatabaseDep,
        user: OptionalUserDep,
        storage: FileStorageDep,
        project_id: int = Path(ge=1),
        document_id: int = Path(ge=1),
):
    """
    Open a project PDF in the browser (`Content-Disposition: inline`). Public for published projects. \\
    Raises 404 Not Found when the project or document does not exist, or the project is a draft
    and the caller is not an admin, or the file is missing from storage; 503 when the storage is unavailable.
    """
    await ProjectRepo(db).get_visible(project_id, include_drafts=user is not None and user.is_admin)
    document = await ProjectDocumentRepo(db).get_for_project(project_id, document_id)

    try:
        content = await storage.open(document.file_path)
    except FileNotFoundError:
        raise NotFoundError(
            resource="ProjectDocument", key={"id": document_id}, loc=("path", "document_id"),
            msg="The file of this document is missing from storage.",
        )
    filename = quote(f"{document.title}.pdf")
    return StreamingResponse(content, media_type="application/pdf", headers={
        "Content-Disposition": f"inline; filename=\"document-{document.id}.pdf\"; filename*=UTF-8''{filename}",
        "Content-Length": str(document.size_bytes),
    })


@router.delete("/{project_id}/documents/{document_id}",
               dependencies=[Depends(get_current_admin)],
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
               status_code=status.HTTP_200_OK,
               summary="Delete project PDF",
               response_description="Successful Response")
async def delete_project_document(
        db: DatabaseDep,
        storage: FileStorageDep,
        project_id: int = Path(ge=1),
        document_id: int = Path(ge=1),
):
    """
    Delete a project PDF and its stored file. Admin only. \\
    Raises 404 Not Found when the project or document does not exist.
    """
    project = await ProjectRepo(db).get_one(id=project_id, key_loc="path")
    await ProjectDocumentRepo(db).delete_document(project_id, document_id, storage)
    if project.status == ProjectStatus.published:
        await index_project(db, project_id)
    return Delete(deleted=1, detail="Deleted ProjectDocument.")


# ============ participants ============


@router.get("/{project_id}/participants",
            dependencies=None,
            response_model=ParticipantsSummary | FeatureCollection[ParticipantProperties],
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get project participants",
            response_description="Successful Response")
async def get_project_participants(
        db: DatabaseDep,
        user: OptionalUserDep,
        level: LevelQuery = None,
        response_format: Literal["json", "geojson"] = Query(
            "json", alias="format", description="`geojson` returns a FeatureCollection for the map.",
        ),
        project_id: int = Path(ge=1),
):
    """
    How many people took part and where they came from. Public for published projects. \\
    JSON: `{total, by_location: [{location_id, name, teryt_code, kind, count}]}`, largest first,
    the unknown origin (all location fields null) last. \\
    `?format=geojson`: a FeatureCollection of the known locations (boundary, or centroid `Point`)
    with `count` in `properties`; the unknown origin is only in the JSON format. \\
    Raises 404 Not Found when the project does not exist, or is a draft and the caller is not an admin.
    """
    await ProjectRepo(db).get_visible(project_id, include_drafts=user is not None and user.is_admin)
    repo = ProjectParticipantRepo(db)
    if response_format == "geojson":
        return await repo.geojson(project_id, level=level)
    return await repo.summary(project_id, level=level)


@router.put("/{project_id}/participants",
            dependencies=[Depends(get_current_admin)],
            response_model=ParticipantsSummary,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Replace project participants",
            response_description="Successful Response")
async def replace_project_participants(
        db: DatabaseDep,
        items: list[ParticipantInput],
        project_id: int = Path(ge=1),
):
    """
    Replace the project's participant counts: `[{location_id, participants_count}]`, one row per
    location (`location_id: null` = unknown origin); locations left out are removed. Admin only. \\
    Returns the new summary. Raises 404 Not Found for a missing project or location,
    422 when a location is listed twice.
    """
    repo = ProjectParticipantRepo(db)
    await repo.replace(project_id, items)
    return await repo.summary(project_id)


# ============ project matches (recommended in the chat) ============

matches_router = APIRouter(
    prefix="/project-matches",
    tags=[Tags.Projects],
    responses={},
)


@matches_router.post("/{match_id}/open",
                     dependencies=None,
                     response_model=ProjectMatchModel,
                     responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
                     status_code=status.HTTP_200_OK,
                     summary="Open project match",
                     response_description="Successful Response")
async def open_project_match(
        db: DatabaseDep,
        actor: VisitorDep,
        match_id: int = Path(ge=1),
):
    """
    Record that the user opened a project card recommended in the chat (`opened = true`). Idempotent. \
    Owner of the conversation only (logged-in owner, the visitor cookie of an anonymous one, or the admin). \
    Raises 404 Not Found when the match does not exist, 403 Forbidden for someone else's conversation.
    """
    return await ProjectMatchRepo(db).open_match(match_id, actor)

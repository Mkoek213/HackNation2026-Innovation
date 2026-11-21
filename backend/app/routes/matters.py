"""Matters ("Moje sprawy"): the logged-in user's own ideas, application inputs and notes."""
from fastapi import APIRouter, Depends, Path, Response, status
from fastapi.responses import JSONResponse

from app.chat.artifacts import assemble
from app.dependencies import DatabaseDep, PaginationDep
from app.exceptions import NotFoundError
from app.models import Conversation, MatterType
from app.repos.matter_repo import MatterRepo, now
from app.repos.workspace_repo import WorkspaceRepo
from app.schemas.default import NOT_FOUND, Delete, ItemList
from app.schemas.matter import MatterCreate, MatterModel, MatterPatch, MatterSummary, MatterThread
from app.services.pdf import pdf_filename, render_markdown_pdf
from app.utils.auth import CurrentUserDep


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/matters", tags=["Matters"], dependencies=[Depends(private_response)])


@router.get("", response_model=ItemList[MatterSummary], summary="Get my matters")
async def get_matters(db: DatabaseDep, user: CurrentUserDep, page: PaginationDep):
    """
    The logged-in user's matters without content, most recently updated first. \
    Paginated with `?limit=&offset=` (`total` is the unpaginated count).
    """
    return await MatterRepo(db).mine(user.id, limit=page.limit, offset=page.offset)


@router.post("", response_model=MatterModel, status_code=status.HTTP_201_CREATED, summary="Create matter")
async def create_matter(db: DatabaseDep, user: CurrentUserDep, data: MatterCreate):
    """
    Create a matter. Without content, the draft types start from their standard section template.
    """
    content = data.content_markdown
    if not (content or "").strip():
        content = "" if data.type == MatterType.note else assemble(data.type.value, [])
    return await MatterRepo(db).add(user.id, title=data.title, type=data.type, status=data.status, content_markdown=content)


@router.get("/{matter_id}", response_model=MatterModel, responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            summary="Get matter")
async def get_matter(db: DatabaseDep, user: CurrentUserDep, matter_id: int = Path(ge=1)):
    """
    One matter with its Markdown content. Read contract for PDF/e-mail export (`id`, `title`, `content_markdown`). \
    Raises 404 Not Found when it does not exist or belongs to another user.
    """
    return await MatterRepo(db).owned(user.id, matter_id)


@router.patch("/{matter_id}", response_model=MatterModel,
              responses={status.HTTP_404_NOT_FOUND: NOT_FOUND,
                         status.HTTP_409_CONFLICT: {"model": MatterModel, "description": "Stale revision; the body is the current matter."}},
              summary="Update matter")
async def update_matter(data: MatterPatch, db: DatabaseDep, user: CurrentUserDep, matter_id: int = Path(ge=1)):
    """
    Compare-and-swap edit of title, status or Markdown content. \
    Raises 409 Conflict with the current matter as the body when `expected_revision` is stale,
    404 Not Found when it does not exist or belongs to another user.
    """
    changes = data.model_dump(exclude_none=True, exclude={"expected_revision"})
    matter, written = await MatterRepo(db).write(user.id, matter_id, data.expected_revision, **changes)
    if not written:
        return JSONResponse(MatterModel.model_validate(matter).model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT,
                            headers={"Cache-Control": "no-store"})
    return matter


@router.delete("/{matter_id}", response_model=Delete, responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
               summary="Delete matter")
async def delete_matter(db: DatabaseDep, user: CurrentUserDep, matter_id: int = Path(ge=1)):
    """Permanently delete a matter. Raises 404 Not Found when it does not exist or belongs to another user."""
    matter = await MatterRepo(db).owned(user.id, matter_id)
    await db.delete(matter)
    await db.commit()
    return Delete(deleted=1, detail="Deleted Matter.")


@router.get("/{matter_id}/pdf", responses={status.HTTP_404_NOT_FOUND: NOT_FOUND}, summary="Download matter as PDF")
async def matter_pdf(db: DatabaseDep, user: CurrentUserDep, matter_id: int = Path(ge=1)):
    """PDF export of the matter title and Markdown body."""
    matter = await MatterRepo(db).owned(user.id, matter_id)
    pdf = render_markdown_pdf(matter.title, matter.content_markdown)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{pdf_filename(matter.title)}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{matter_id}/thread", response_model=MatterThread, responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
             summary="Open matter thread")
async def matter_thread(db: DatabaseDep, user: CurrentUserDep, matter_id: int = Path(ge=1)):
    """
    The workspace thread for chatting about this matter: the linked thread when it is still active and owned
    by the user, otherwise a new thread titled after the matter, which becomes the linked one.
    """
    repo = MatterRepo(db)
    matter = await repo.owned(user.id, matter_id, lock=True)
    if matter.conversation_id is not None:
        try:
            await WorkspaceRepo(db).owned(user.id, matter.conversation_id)
            await db.commit()
            return MatterThread(conversation_id=matter.conversation_id)
        except NotFoundError:
            pass
    thread = Conversation(user_id=user.id, workspace=True, title=matter.title, last_activity_at=now())
    db.add(thread)
    await db.flush()
    await repo.link(matter, thread.id)
    return MatterThread(conversation_id=thread.id)

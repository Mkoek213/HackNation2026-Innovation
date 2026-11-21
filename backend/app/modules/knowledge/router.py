"""HTTP operations of the knowledge module (prefix /api/v1/knowledge)."""
import hmac
import json
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from anyio import to_thread
from fastapi.responses import StreamingResponse

from fastapi import (APIRouter, Depends, File, Form, Header, HTTPException, Path as PathParam, Query, Request,
                     UploadFile, status)
from pydantic import BaseModel, ValidationError

from app.dependencies import DatabaseDep
from app.utils.auth import get_optional_user

from .draft import NoReadableText, propose_from_files
from .errors import InnovationNotFound, KnowledgeUnavailable
from .schemas import (
    INNOVATION_ID_PATTERN,
    CategoriesUpdate,
    Deleted,
    IngestResult,
    InnovationDraft,
    InnovationMeta,
    InnovationSummary,
    InnovationUpdate,
)
from .service import KnowledgeService, get_knowledge_service
from .settings import load_knowledge_settings
from .taxonomy import (CATEGORY_LABELS, INNOVATION_TYPE_LABELS, INSTITUTION_TYPE_LABELS, MATURITY_LABELS,
                       Category)

ADMIN_TOKEN_HEADER = "X-Admin-Token"


class ErrorResponse(BaseModel):
    detail: str


async def knowledge_service() -> KnowledgeService:
    try:
        return await get_knowledge_service()
    except KnowledgeUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


async def require_admin(request: Request, db: DatabaseDep,
                        x_admin_token: Annotated[str | None, Header(alias=ADMIN_TOKEN_HEADER)] = None) -> None:
    """Demo-grade protection for writes: a logged-in admin session (the admin panel), or the shared
    secret from RADAR_ADMIN_TOKEN for scripts. Not a substitute for real authorization."""
    expected = load_knowledge_settings().admin_token
    if expected is not None and x_admin_token is not None \
            and hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        return
    user = await get_optional_user(request, db)
    if user is not None and user.is_admin:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, f"Admin session or valid {ADMIN_TOKEN_HEADER} required.")


@contextmanager
def _not_found() -> Iterator[None]:
    try:
        yield
    except KnowledgeUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    except InnovationNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


Service = Annotated[KnowledgeService, Depends(knowledge_service)]
InnovationId = Annotated[str, PathParam(pattern=INNOVATION_ID_PATTERN, max_length=120)]

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["Baza wiedzy"],
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse, "description": "Knowledge base unavailable"}},
)
_admin = {
    "dependencies": [Depends(require_admin)],
    "responses": {status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Missing or invalid admin token"}},
}
_not_found_response = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Innovation not found"}}


@router.get("/categories", response_model=dict[Category, str], summary="Sektory innowacji")
def get_categories() -> dict[Category, str]:
    """Sector slugs with Polish labels. Needs no knowledge base."""
    return CATEGORY_LABELS


class Taxonomy(BaseModel):
    sectors: dict[str, str]
    innovation_types: dict[str, str]
    institution_types: dict[str, str]
    maturity: dict[str, str]


@router.get("/taxonomy", response_model=Taxonomy, summary="Osie klasyfikacji innowacji")
def get_taxonomy() -> Taxonomy:
    """Polish labels of every classification axis. Needs no knowledge base."""
    return Taxonomy(sectors=CATEGORY_LABELS, innovation_types=INNOVATION_TYPE_LABELS,
                    institution_types=INSTITUTION_TYPE_LABELS, maturity=MATURITY_LABELS)


async def _save_uploads(files: list[UploadFile], directory: Path) -> list[Path]:
    max_bytes = load_knowledge_settings().max_upload_mb * 1024 * 1024
    saved: list[Path] = []
    for i, upload in enumerate(files):
        name = Path(upload.filename or "").name or f"upload-{i}"  # drop client-supplied directories
        folder = directory / str(i)
        folder.mkdir(parents=True)
        dest = folder / name
        size = 0
        with open(dest, "wb") as out:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Plik przekracza limit rozmiaru.")
                await to_thread.run_sync(out.write, chunk)
        saved.append(dest)
    return saved


@router.get("/innovations",response_model=list[InnovationSummary], summary="Lista innowacji")
async def list_innovations(service: Service, category: Category | None = Query(default=None)):
    return await service.list_innovations(category)


@router.post("/innovations/draft", response_model=InnovationDraft, summary="Uzupełnij kartę z dokumentów", **_admin)
async def draft_innovation(files: Annotated[list[UploadFile], File(description="PDF, DOCX or ZIP documents")]):
    """Read uploaded documents and propose a title, Polish card and sectors.

    Categories are a GLiDE decision. The card text is written by the chat model.
    Nothing is stored, and Qdrant is not required.
    """
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Dodaj co najmniej jeden plik.")
    with tempfile.TemporaryDirectory(prefix="knowledge-draft-") as tmp:
        root = Path(tmp)
        try:
            saved = await _save_uploads(files, root / "uploads")
            return await propose_from_files(saved, root / "work")
        except NoReadableText as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        except ValueError as e:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(e)) from e
        except (OSError, zipfile.BadZipFile) as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nieprawidłowy dokument lub archiwum.") from e


@router.get("/innovations/{innovation_id}", response_model=InnovationSummary,
            responses=_not_found_response, summary="Innowacja")
async def get_innovation(service: Service, innovation_id: InnovationId):
    with _not_found():
        return await service.get(innovation_id)


@router.put("/innovations/{innovation_id}", response_model=IngestResult, summary="Dodaj lub zastąp innowację",
            **_admin)
async def put_innovation(
        service: Service,
        innovation_id: InnovationId,
        meta: Annotated[str, Form(
            description="InnovationMeta as JSON; `id` is taken from the path.",
            examples=['{"title": "Czujnik jakości powietrza dla szkół", "primary_category": "jakosc-zycia", "categories": ["jakosc-zycia", "ict"], '
                      '"card": {"solution": "..."}}'],
        )],
        files: Annotated[list[UploadFile], File(description="Full materials: PDF, DOCX or ZIP documents")] = [],
        summary: Annotated[UploadFile | None, File(description="Short overview of the innovation: one PDF or DOCX")] = None,
):
    """
    Upload the innovation card, its short `summary` document and its full materials (`files`).
    Text is extracted with page numbers, split into section-aware chunks, embedded (dense + BM25) and
    written to Qdrant, replacing any previous version of this innovation; documents go to S3.
    The card and summary decide which innovations match a need; full materials supply the cited
    evidence. Vectors are computed before the old version is removed, so a failed upload keeps the
    published one. Scans without a text layer are listed in `skipped_files` (no OCR).
    """
    try:
        data = json.loads(meta)
        if not isinstance(data, dict):
            raise ValueError("meta must be a JSON object")
        parsed = InnovationMeta.model_validate({**data, "id": innovation_id})
    except (ValueError, ValidationError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid meta: {e}") from e

    if summary is not None and Path(summary.filename or "").suffix.lower() not in {".pdf", ".docx"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Podsumowanie musi być plikiem PDF lub DOCX.")

    with tempfile.TemporaryDirectory(prefix="knowledge-") as tmp:
        upload_dir = Path(tmp) / "uploads"
        upload_dir.mkdir()
        saved = await _save_uploads(files, upload_dir / "files")
        summary_path = (await _save_uploads([summary], upload_dir / "summary"))[0] if summary is not None else None
        try:
            with _not_found():
                return await service.ingest(parsed, saved, Path(tmp) / "work", summary=summary_path)
        except ValueError as e:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(e)) from e
        except (OSError, zipfile.BadZipFile) as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nieprawidłowy dokument lub archiwum.") from e


@router.patch("/innovations/{innovation_id}", response_model=InnovationSummary, summary="Zmień kartę innowacji",
              dependencies=_admin["dependencies"], responses={**_admin["responses"], **_not_found_response})
async def update_innovation(service: Service, innovation_id: InnovationId, update: InnovationUpdate):
    """Replace the title, categories, links and card text, keeping the indexed documents.
    To replace the documents, use `PUT /innovations/{innovation_id}`."""
    with _not_found():
        return await service.update(innovation_id, update)


@router.patch("/innovations/{innovation_id}/categories", response_model=InnovationSummary,
              summary="Zmień kategorie innowacji",
              dependencies=_admin["dependencies"], responses={**_admin["responses"], **_not_found_response})
async def update_categories(service: Service, innovation_id: InnovationId, update: CategoriesUpdate):
    """Updates the card and every chunk, so category filters apply immediately. No re-embedding."""
    with _not_found():
        return await service.update_categories(innovation_id, update)


@router.delete("/innovations/{innovation_id}", response_model=Deleted, summary="Usuń innowację",
               dependencies=_admin["dependencies"], responses={**_admin["responses"], **_not_found_response})
async def delete_innovation(service: Service, innovation_id: InnovationId):
    with _not_found():
        await service.delete(innovation_id)
    return Deleted(deleted=innovation_id)


@router.get("/innovations/{innovation_id}/documents/{document_id}",
            responses=_not_found_response, summary="Pobierz dokument innowacji")
async def get_document(service: Service, innovation_id: InnovationId,
                       document_id: Annotated[str, PathParam(pattern=r"^[a-f0-9]{32}$")]):
    with _not_found():
        innovation = await service.get(innovation_id)
        document = next((d for d in innovation.documents if d.id == document_id), None)
        if document is None:
            raise HTTPException(404, "Nie znaleziono dokumentu.")
        try:
            body = await to_thread.run_sync(service.documents.open, document)
        except FileNotFoundError as e:
            raise HTTPException(404, "Nie znaleziono dokumentu.") from e

    async def stream():
        try:
            while chunk := await to_thread.run_sync(body.read, 64 * 1024):
                yield chunk
        finally:
            body.close()

    disposition = "inline" if document.content_type == "application/pdf" else "attachment"
    return StreamingResponse(stream(), media_type=document.content_type, headers={
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(document.filename, safe='')}",
        "Content-Length": str(document.size_bytes),
        "X-Content-Type-Options": "nosniff",
    })

"""Operator (PCI) staff directory and shared PDF helper used by communication flows."""

from fastapi import APIRouter, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.config import settings
from app.dependencies import DatabaseDep
from app.docs import Tags
from app.models import User, UserRole
from app.schemas.workspace import MarkdownPdf, StaffContact
from app.services.pdf import pdf_filename, render_markdown_pdf
from app.utils.auth import CurrentUserDep

router = APIRouter(prefix="/operator", tags=[Tags.Operator])


class StaffList(BaseModel):
    items: list[StaffContact]
    model_config = ConfigDict(extra="forbid")


@router.get("/staff", response_model=StaffList, summary="List operator staff e-mail addresses")
async def list_staff(db: DatabaseDep, user: CurrentUserDep):
    """Admins with a profile e-mail, plus optional `RADAR_CONTACT_EMAIL`."""
    del user  # Auth only.
    rows = (await db.scalars(
        select(User).where(User.role == UserRole.admin, User.email.is_not(None)).order_by(User.username),
    )).all()
    seen: set[str] = set()
    items: list[StaffContact] = []
    configured = (settings.radar_contact_email or "").strip().lower()
    if configured:
        items.append(StaffContact(name="PCI (kontakt główny)", email=configured))
        seen.add(configured)
    for row in rows:
        email = (row.email or "").strip().lower()
        if not email or email in seen:
            continue
        items.append(StaffContact(name=row.username, email=email))
        seen.add(email)
    return StaffList(items=items)


@router.post("/pdf", summary="Generate PDF from Markdown", status_code=status.HTTP_200_OK)
async def markdown_pdf(user: CurrentUserDep, data: MarkdownPdf):
    """Authenticated helper for case/artifact PDF export (title + Markdown body)."""
    del user
    pdf = render_markdown_pdf(data.title, data.content)
    name = pdf_filename(data.title)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )

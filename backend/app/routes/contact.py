"""Public contact form ("Kontakt"): messages to operator staff without starting a chat."""
import asyncio
import logging
import smtplib

from fastapi import APIRouter, Depends, Request, Response, status

from app.config import settings
from app.dependencies import DatabaseDep, PaginationDep
from app.docs import Tags
from app.middlewares.limiter import limiter
from app.repos.contact_repo import ContactRepo
from app.schemas.contact import ContactCreate, ContactModel, ContactReceipt
from app.schemas.default import ItemList
from app.services.mail import contact_message, deliver, mail_delivery_available
from app.utils.auth import CurrentAdminDep, OptionalUserDep

logger = logging.getLogger(__name__)


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/contact", tags=[Tags.Operator], dependencies=[Depends(private_response)])


@router.post("",
             response_model=ContactReceipt,
             status_code=status.HTTP_201_CREATED,
             summary="Send contact message")
@limiter.limit(settings.contact_rate_limit)
async def send_contact_message(
        request: Request,
        response: Response,
        db: DatabaseDep,
        user: OptionalUserDep,
        data: ContactCreate,
):
    """
    Public contact form: name, e-mail, message and the required `consent: true`. \\
    The message is always stored; when SMTP and `RADAR_CONTACT_EMAIL` are configured it is also e-mailed
    to the operator with `Reply-To` set to the sender. A delivery failure is logged and does not fail the request,
    because staff still see the stored message (`GET /contact`). \\
    Links the message to the logged-in user, if any. Rate limited by `CONTACT_RATE_LIMIT` per IP.
    """
    repo = ContactRepo(db)
    saved = await repo.create(data, exclude={"consent"}, user_id=user.id if user else None)
    await db.refresh(saved)
    recipient = settings.radar_contact_email.strip()
    if recipient and mail_delivery_available():
        mail = contact_message(recipient=recipient, name=saved.name, email=saved.email, body=saved.message)
        try:
            await asyncio.to_thread(deliver, mail)
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning("Contact message %s was stored but not e-mailed: %s", saved.id, type(exc).__name__)
        else:
            await repo.mark_delivered(saved.id)
    return saved


@router.get("", response_model=ItemList[ContactModel], summary="Get contact messages")
async def get_contact_messages(db: DatabaseDep, admin: CurrentAdminDep, page: PaginationDep):
    """
    Contact form messages, newest first. Admin only. \\
    Paginated with `?limit=&offset=` (`total` is the unpaginated count).
    """
    del admin  # Auth only.
    return await ContactRepo(db).newest(limit=page.limit, offset=page.offset)

"""Messages sent through the public contact form ("Kontakt")."""
import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base, BigIntPK

CONTACT_NAME_MAX_LENGTH = 120
CONTACT_EMAIL_MAX_LENGTH = 254
CONTACT_MESSAGE_MAX_LENGTH = 5000


class ContactMessage(Base):
    """
    One contact form submission. It is stored first, so a message is never lost when mail delivery
    fails; `delivered` records whether it was also e-mailed to `RADAR_CONTACT_EMAIL`.
    The sender agreed to processing their data to get an answer (the form requires consent).
    Deleting the user keeps the message, which carries its own name and e-mail.
    """
    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    name: Mapped[str] = mapped_column(String(CONTACT_NAME_MAX_LENGTH))
    email: Mapped[str] = mapped_column(String(CONTACT_EMAIL_MAX_LENGTH))
    message: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="SET NULL"), default=None,
    )
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import mapped_column, Mapped

from app.database.database import Base, BigIntPK

#: Maximum stored length of `visits.path`.
VISIT_PATH_MAX_LENGTH = 512


class Visit(Base):
    """
    One page view reported by the frontend (`POST /visits`), the source of the site usage
    statistics. Only the path is stored (no query string, no IP address).
    Deleting the user keeps the visit for the statistics, counted by its visitor id.
    """
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    visitor_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    user_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="SET NULL"), default=None,
    )
    path: Mapped[str] = mapped_column(String(VISIT_PATH_MAX_LENGTH))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

"""Project-independent volunteer profiles and automatic topic assignments."""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base, BigIntPK


class VolunteerProfile(Base):
    __tablename__ = "volunteer_profiles"

    user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    classification: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=None)
    # Explicit self-selected tags (app.modules.tester_tags), independent of the automatic topic tags.
    roles: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=list, server_default="[]")
    interests: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=list, server_default="[]")
    consented_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VolunteerTag(Base):
    __tablename__ = "volunteer_tags"

    user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("volunteer_profiles.user_id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True)

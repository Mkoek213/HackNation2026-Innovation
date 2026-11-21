"""Applications of pool testers to test a knowledge-base innovation, reviewed by admins."""
import datetime as dt
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base, BigIntPK


class ApplicationStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ApplicationSource(StrEnum):
    tester = "tester"  # the tester applied
    admin = "admin"  # an admin assigned the tester directly


class TesterApplication(Base):
    __tablename__ = "tester_applications"
    __table_args__ = (
        UniqueConstraint("user_id", "innovation_id", name="uq_tester_applications_user_innovation"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("volunteer_profiles.user_id", ondelete="CASCADE"), index=True)
    # Knowledge innovation slug (Qdrant), not projects.id; a deleted innovation leaves the row with its slug.
    innovation_id: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="tester_application_status", native_enum=False, length=16, create_constraint=True),
        default=ApplicationStatus.pending,
    )
    source: Mapped[ApplicationSource] = mapped_column(
        Enum(ApplicationSource, name="tester_application_source", native_enum=False, length=16, create_constraint=True),
        default=ApplicationSource.tester,
    )
    message: Mapped[str | None] = mapped_column(Text, default=None)
    decided_by: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="SET NULL"), default=None)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

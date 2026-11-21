import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, Text, UniqueConstraint, func
from sqlalchemy.orm import mapped_column, Mapped

from app.database.database import Base, BigIntPK


class TestSignup(Base):
    """
    A logged-in user's willingness to test a published project; one per (project, user).
    Removed with the project or the user; deleting the location only clears it.
    """
    __tablename__ = "test_signups"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_test_signups_project_id_user_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Where the tester comes from (voluntary).
    location_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("locations.id", ondelete="SET NULL"), default=None,
    )
    message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectReview(Base):
    """
    A logged-in user's rating (1-5) of a published project with optional feedback
    or improvement suggestions; one per (project, user), updated in place.
    """
    __tablename__ = "project_reviews"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_reviews_project_id_user_id"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_project_reviews_rating_range"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

import datetime as dt
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import mapped_column, Mapped

from app.database.database import Base, BigIntPK


class IdeaStage(StrEnum):
    idea = "idea"
    prototype = "prototype"
    micro_scale_test = "micro_scale_test"
    implemented = "implemented"


class IdeaStatus(StrEnum):
    submitted = "submitted"
    published = "published"
    rejected = "rejected"


class Idea(Base):
    """
    Idea creator card (fiszka) submitted by a logged-in user and reviewed by the admin.
    Only `published` ideas are public. Deleting the author deletes their ideas;
    deleting a referenced tag or location only clears the reference.
    """
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    author_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column()
    # What the idea is about.
    essence: Mapped[str] = mapped_column(Text)
    # Who it is for.
    target_group: Mapped[str] = mapped_column(Text)
    stage: Mapped[IdeaStage] = mapped_column(
        Enum(IdeaStage, name="idea_stage", native_enum=False, length=16, create_constraint=True),
    )
    tag_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("tags.id", ondelete="SET NULL"), index=True, default=None,
    )
    location_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("locations.id", ondelete="SET NULL"), default=None,
    )
    status: Mapped[IdeaStatus] = mapped_column(
        Enum(IdeaStatus, name="idea_status", native_enum=False, length=16, create_constraint=True),
        index=True,
        default=IdeaStatus.submitted,
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

"""Matters ("sprawy"): user-owned ideas, application inputs and notes kept under "Moje sprawy"."""
import datetime as dt
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base, BigIntPK


class MatterType(StrEnum):
    idea_card = "idea_card"
    application_draft = "application_draft"
    adaptation_plan = "adaptation_plan"
    note = "note"


class MatterStatus(StrEnum):
    draft = "draft"
    ready = "ready"
    sent = "sent"


class Matter(Base):
    """
    A Markdown document owned by one user, edited by hand or by the workspace agent.
    Every write is a compare-and-swap on `revision`, so concurrent edits are never silently lost.
    Deleting the user deletes their matters; archiving or deleting the linked thread only clears the link.
    """
    __tablename__ = "matters"
    __table_args__ = (
        Index("ix_matters_user_id_updated_at", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[MatterType] = mapped_column(
        Enum(MatterType, name="matter_type", native_enum=False, length=32, create_constraint=True),
    )
    status: Mapped[MatterStatus] = mapped_column(
        Enum(MatterStatus, name="matter_status", native_enum=False, length=16, create_constraint=True),
        default=MatterStatus.draft,
    )
    content_markdown: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=1)
    conversation_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("conversations.id", ondelete="SET NULL"), default=None,
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

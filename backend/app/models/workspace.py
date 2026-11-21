"""Durable submission state. One operation represents one user/assistant pair."""
import datetime as dt

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base, BigIntPK
from app.models.conversation import SourcesType


class ChatOperation(Base):
    __tablename__ = "chat_operations"
    __table_args__ = (
        UniqueConstraint("conversation_id", "key", name="uq_chat_operations_key"),
        CheckConstraint("status IN ('processing', 'completed', 'failed')", name="ck_chat_operations_status"),
        Index("uq_chat_operations_pending", "conversation_id", unique=True,
              sqlite_where=text("status = 'processing'"), postgresql_where=text("status = 'processing'")),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("conversations.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(36))
    user_message_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("messages.id", ondelete="CASCADE"))
    assistant_message_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("messages.id", ondelete="CASCADE"), default=None)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="processing")
    attempt: Mapped[str] = mapped_column(String(36))
    result: Mapped[dict | None] = mapped_column(SourcesType, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class InnovationMatch(Base):
    """
    A knowledge-base innovation shown in a workspace thread; the workspace counterpart of
    `project_matches`. One row per (thread, innovation), so repeated answers do not inflate counts.
    `innovation_id` is the knowledge-base id, not a `projects` row.
    """
    __tablename__ = "innovation_matches"
    __table_args__ = (
        UniqueConstraint("conversation_id", "innovation_id", name="uq_innovation_matches_conversation_innovation"),
        Index("ix_innovation_matches_innovation_id_created_at", "innovation_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("conversations.id", ondelete="CASCADE"))
    innovation_id: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(Text)
    opened: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

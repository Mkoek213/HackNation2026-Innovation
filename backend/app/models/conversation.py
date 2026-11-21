import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, JSON, Text, UniqueConstraint, Uuid, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.database.database import Base, BigIntPK


class ConversationKind(StrEnum):
    search = "search"  # matchmaking (default)
    idea_assistant = "idea_assistant"
    middleman = "middleman"


class ConversationStatus(StrEnum):
    active = "active"
    archived = "archived"


class ConversationOutcome(StrEnum):
    answered = "answered"
    partially_answered = "partially_answered"
    no_answer = "no_answer"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"


class TagSource(StrEnum):
    ai = "ai"  # assigned by the ChatEngine, replaced after every answer
    manual = "manual"  # set by the owner or admin (PUT /conversations/{id}/tags)


#: Message sources column: jsonb on PostgreSQL, JSON (text) on SQLite.
SourcesType = JSON().with_variant(JSONB(), "postgresql")


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, native_enum=False, length=32, create_constraint=True)


class Conversation(Base):
    """
    An LLM conversation. Saved (with messages and a title) only when started by a logged-in
    user (`user_id`). An anonymous conversation is a content-free row owned by the
    `visitor_id` cookie, kept for statistics with its tags, matches and outcome.
    """
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_id_last_activity_at", "user_id", "last_activity_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    classification: Mapped[dict[str, Any] | None] = mapped_column(SourcesType, default=None)
    workspace: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    user_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), default=None,
    )
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, default=None)
    kind: Mapped[ConversationKind] = mapped_column(
        _enum(ConversationKind, "conversation_kind"), default=ConversationKind.search,
    )
    title: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[ConversationStatus] = mapped_column(
        _enum(ConversationStatus, "conversation_status"), default=ConversationStatus.active,
    )
    outcome: Mapped[ConversationOutcome | None] = mapped_column(
        _enum(ConversationOutcome, "conversation_outcome"), default=None,
    )
    location_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("locations.id", ondelete="SET NULL"), index=True, default=None,
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_activity_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # `last_activity_at` covered by the stored topic tags; older than it means tagging is due.
    tagged_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Children are removed by ON DELETE CASCADE in the database.
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.id", cascade="all, delete-orphan", passive_deletes=True,
    )
    tags: Mapped[list["ConversationTag"]] = relationship(
        back_populates="conversation", order_by="ConversationTag.id", cascade="all, delete-orphan", passive_deletes=True,
    )
    matches: Mapped[list["ProjectMatch"]] = relationship(
        back_populates="conversation", order_by="ProjectMatch.id", cascade="all, delete-orphan", passive_deletes=True,
    )

    @property
    def saved(self) -> bool:
        """Whether messages and the title are stored (started while logged in)."""
        return self.user_id is not None


class Message(Base):
    """A message of a saved conversation. Never stored for anonymous conversations."""
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole, "message_role"))
    content: Mapped[str] = mapped_column(Text)
    # References returned by the external vector DB: [{title, url, page, excerpt}].
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(SourcesType, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ConversationTag(Base):
    """
    A tag (and optionally a more specific subtag of it) of a conversation.
    `tag_id` is always set, so tag statistics are a plain GROUP BY tag_id.
    One row per (conversation, tag, subtag); the repo enforces it for a NULL subtag on SQLite.
    """
    __tablename__ = "conversation_tags"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "tag_id", "subtag_id",
            name="uq_conversation_tags_conversation_id_tag_id_subtag_id",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("conversations.id", ondelete="CASCADE"))
    tag_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("tags.id", ondelete="RESTRICT"), index=True)
    subtag_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("subtags.id", ondelete="RESTRICT"), index=True, default=None,
    )
    source: Mapped[TagSource] = mapped_column(_enum(TagSource, "conversation_tag_source"), default=TagSource.ai)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="tags")


class ProjectMatch(Base):
    """
    A project recommended in a conversation; the source of "how many people searched
    for this project". One row per (conversation, project), so repeated recommendations
    do not inflate the counts.
    """
    __tablename__ = "project_matches"
    __table_args__ = (
        UniqueConstraint("conversation_id", "project_id", name="uq_project_matches_conversation_id_project_id"),
        Index("ix_project_matches_project_id_created_at", "project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("projects.id", ondelete="RESTRICT"))
    conversation_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("conversations.id", ondelete="CASCADE"))
    opened: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="matches")

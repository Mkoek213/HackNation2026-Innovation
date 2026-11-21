"""Additive chat tables; anonymous identities are distinct from login accounts."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class ChatOwner(Base):
    __tablename__ = "chat_owners"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("chat_owners.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active_turn: Mapped[str | None] = mapped_column(String(36), nullable=True)
    next_position: Mapped[int] = mapped_column(default=1)


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (UniqueConstraint("owner_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("chat_owners.id"))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    user_message_id: Mapped[str] = mapped_column(String(36))
    assistant_message_id: Mapped[str] = mapped_column(String(36))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "position"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column()
    turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatArtifact(Base):
    """Latest-only editable draft; the revision counter guards compare-and-swap writes."""
    __tablename__ = "chat_artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    content_markdown: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column()
    innovation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatGuide(Base):
    """Progressive case facts and separate advisory notes; no required intake stages."""
    __tablename__ = "chat_guides"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

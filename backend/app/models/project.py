import datetime as dt
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Double, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.database.database import Base, BigIntPK


class ProjectStatus(StrEnum):
    draft = "draft"
    published = "published"  # visible to the public and sent to the vector DB


class Project(Base):
    """
    A social innovation or project, recommended in the chat.
    One main tag and an optional subtag of that tag.
    """
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    title: Mapped[str] = mapped_column()
    summary: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)  # markdown
    website_url: Mapped[str | None] = mapped_column(default=None)
    video_url: Mapped[str | None] = mapped_column(default=None)
    tag_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("tags.id", ondelete="RESTRICT"), index=True)
    subtag_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("subtags.id", ondelete="RESTRICT"), index=True, default=None,
    )
    location_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("locations.id"), index=True, default=None)
    # Map marker; the location centroid is used when not set.
    latitude: Mapped[float | None] = mapped_column(Double, default=None)
    longitude: Mapped[float | None] = mapped_column(Double, default=None)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status", native_enum=False, length=16, create_constraint=True),
        default=ProjectStatus.draft,
        index=True,
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # Children are removed by ON DELETE CASCADE in the database.
    documents: Mapped[list["ProjectDocument"]] = relationship(
        back_populates="project",
        order_by="ProjectDocument.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    participants: Mapped[list["ProjectParticipant"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Read-only usages, so ProjectRepo.protect_on_delete can block deleting a project
    # that was recommended in conversations (it is part of the statistics).
    matches: Mapped[list["ProjectMatch"]] = relationship(viewonly=True)


class ProjectDocument(Base):
    """
    A PDF attached to a project. The file lives in file storage (app.services.files);
    `file_path` is its backend-agnostic storage key.
    """
    __tablename__ = "project_documents"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column()  # accessible link text
    file_path: Mapped[str] = mapped_column()
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="documents")


class ProjectParticipant(Base):
    """
    How many people took part in a project, per location (NULL = unknown).
    One row per (project, location); the repo enforces it for the NULL location on SQLite.
    """
    __tablename__ = "project_participants"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "location_id",
            name="uq_project_participants_project_id_location_id",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("participants_count >= 0", name="ck_project_participants_count_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("projects.id", ondelete="CASCADE"))
    location_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("locations.id"), index=True, default=None)
    participants_count: Mapped[int] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="participants")

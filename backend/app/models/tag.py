from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.database.database import Base, BigIntPK


class Tag(Base):
    """
    Admin-defined topic used to classify conversations and projects.
    `description` is also given to the LLM as the label definition.
    """
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    subtags: Mapped[list["Subtag"]] = relationship(
        back_populates="tag",
        order_by="Subtag.id",
        passive_deletes="all",
    )
    # Read-only usages, so TagRepo.protect_on_delete can block deleting a tag in use.
    projects: Mapped[list["Project"]] = relationship(viewonly=True)
    conversation_tags: Mapped[list["ConversationTag"]] = relationship(viewonly=True)


class Subtag(Base):
    """
    More specialised topic that always belongs to exactly one tag.
    """
    __tablename__ = "subtags"
    __table_args__ = (
        UniqueConstraint("tag_id", "name", name="uq_subtags_tag_id_name"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    tag_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("tags.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column()
    description: Mapped[str | None] = mapped_column(Text, default=None)

    tag: Mapped[Tag] = relationship(back_populates="subtags")
    # Read-only usages, so SubtagRepo.protect_on_delete can block deleting a subtag in use.
    projects: Mapped[list["Project"]] = relationship(viewonly=True)
    conversation_tags: Mapped[list["ConversationTag"]] = relationship(viewonly=True)

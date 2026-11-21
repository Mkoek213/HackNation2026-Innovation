import datetime as dt
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.conversation import (
    ConversationKind,
    ConversationOutcome,
    ConversationStatus,
    MessageRole,
    TagSource,
)
from app.schemas.tagging import Classification
from app.schemas.project import ProjectModel
from app.schemas.tag import Name
from app.utils.schemas_decorators import update_model

#: Limits of the client-supplied transcript of an anonymous conversation (D4).
HISTORY_MAX_TURNS = 10
HISTORY_MAX_CHARS = 8000
MESSAGE_MAX_CHARS = 4000


class HistoryTurn(BaseModel):
    """One earlier message of an anonymous conversation, kept by the client."""
    role: MessageRole = Field(examples=[MessageRole.user])
    content: str = Field(min_length=1, max_length=HISTORY_MAX_CHARS, examples=["Szukam rozwiązania do monitorowania jakości powietrza w szkole."])

    model_config = ConfigDict(extra="forbid")


def _history_size(history: list[HistoryTurn]) -> list[HistoryTurn]:
    total = sum(len(turn.content) for turn in history)
    if total > HISTORY_MAX_CHARS:
        raise ValueError(f"History may contain at most {HISTORY_MAX_CHARS} characters in total, got {total}.")
    return history


History = Annotated[
    list[HistoryTurn],
    Field(max_length=HISTORY_MAX_TURNS),
    AfterValidator(_history_size),
]


class SourceModel(BaseModel):
    """A reference returned by the vector DB that the answer relies on."""
    title: str = Field(examples=["Spółdzielnia sąsiedzka"])
    url: str | None = Field(default=None, examples=["/projects/1"])
    page: int | None = Field(default=None, examples=[None])
    excerpt: str | None = Field(default=None, examples=["Uczniowie budują czujniki jakości powietrza dla szkół."])


class ConversationTagModel(BaseModel):
    tag_id: int = Field(ge=1, examples=[1])
    subtag_id: int | None = Field(default=None, examples=[None])
    source: TagSource = Field(examples=[TagSource.ai])

    model_config = ConfigDict(from_attributes=True)


class ConversationTagInput(BaseModel):
    tag_id: int = Field(ge=1, examples=[1])
    subtag_id: int | None = Field(default=None, ge=1, examples=[None])

    model_config = ConfigDict(extra="forbid")


class ConversationModel(BaseModel):
    """A conversation without its messages. `saved` = started while logged in, so messages
    and the title are stored; anonymous conversations have no title and no messages."""
    id: int = Field(ge=1, examples=[1])
    kind: ConversationKind = Field(examples=[ConversationKind.search])
    title: str | None = Field(default=None, examples=["Czujniki powietrza w szkołach w Rzeszowie"])
    status: ConversationStatus = Field(examples=[ConversationStatus.active])
    outcome: ConversationOutcome | None = Field(default=None, examples=[ConversationOutcome.answered])
    location_id: int | None = Field(default=None, examples=[None])
    saved: bool = Field(examples=[True])
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])
    last_activity_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])
    tags: list[ConversationTagModel] = Field(default_factory=list)
    classification: Classification | None = None

    model_config = ConfigDict(from_attributes=True)


class MessageModel(BaseModel):
    id: int = Field(ge=1, examples=[1])
    role: MessageRole = Field(examples=[MessageRole.assistant])
    content: str = Field(examples=["Znalazłem w bazie Radaru 1 innowację, która może pomóc."])
    sources: list[SourceModel] | None = Field(default=None)
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])

    model_config = ConfigDict(from_attributes=True)


class ProjectMatchModel(BaseModel):
    """A project recommended in a conversation. `id` is the match id for
    `POST /project-matches/{id}/open`; `project` is the project card."""
    id: int = Field(ge=1, examples=[1])
    project_id: int = Field(ge=1, examples=[1])
    conversation_id: int = Field(ge=1, examples=[1])
    opened: bool = Field(examples=[False])
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])
    project: ProjectModel


class ConversationDetail(ConversationModel):
    """A conversation with its messages (empty when not saved) and recommended projects."""
    messages: list[MessageModel] = Field(default_factory=list)
    projects: list[ProjectMatchModel] = Field(default_factory=list)


class AssistantReply(BaseModel):
    """
    The answer to one user message. `message_id` is null for anonymous conversations
    (nothing is stored). `projects` are the projects recommended in this answer;
    `tags` and `outcome` are the conversation's state after it.
    """
    message_id: int | None = Field(default=None, examples=[2])
    content: str = Field(examples=["Znalazłem w bazie Radaru 1 innowację, która może pomóc."])
    sources: list[SourceModel] = Field(default_factory=list)
    projects: list[ProjectMatchModel] = Field(default_factory=list)
    tags: list[ConversationTagModel] = Field(default_factory=list)
    outcome: ConversationOutcome = Field(examples=[ConversationOutcome.answered])


class ConversationStart(BaseModel):
    """`POST /conversations` result: the new conversation and the first answer."""
    conversation: ConversationModel
    answer: AssistantReply


class ConversationCreate(BaseModel):
    message: Name = Field(min_length=1, max_length=MESSAGE_MAX_CHARS, examples=["Szukam czujników jakości powietrza dla szkół w Rzeszowie."])
    kind: ConversationKind = Field(default=ConversationKind.search, examples=[ConversationKind.search])
    location_id: int | None = Field(default=None, ge=1, examples=[None])

    model_config = ConfigDict(extra="forbid")


class MessageCreate(BaseModel):
    """A new user message. `history` is only read for anonymous conversations
    (the client keeps their transcript); saved conversations use the stored messages."""
    content: Name = Field(min_length=1, max_length=MESSAGE_MAX_CHARS, examples=["A coś dla ich opiekunów?"])
    history: History = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class _ConversationEditable(BaseModel):
    title: Name = Field(min_length=1, max_length=200, examples=["Czujniki powietrza w szkołach"])
    status: ConversationStatus = Field(examples=[ConversationStatus.archived])
    location_id: int = Field(ge=1, examples=[1])


@update_model(nullable=("title", "location_id"))
class ConversationUpdate(_ConversationEditable):
    """All fields optional; `title` and `location_id` can be cleared with null."""
    pass

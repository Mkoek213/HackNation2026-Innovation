"""Frozen frontend contracts. Storage, authorization and evidence checks remain services."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter,
    model_validator,
)

from app.modules.knowledge import Evidence

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
ArtifactType = Literal["idea_card", "application_draft", "adaptation_plan"]
ARTIFACT_MAX_CHARS = 20000
TurnStatus = Literal["running", "completed", "failed", "interrupted"]
ErrorCode = Literal[
    "invalid_input", "not_found", "artifact_revision_conflict", "request_id_conflict",
    "turn_in_progress", "service_unavailable", "provider_error", "turn_timeout",
    "budget_exceeded", "turn_interrupted",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ChatRequest(Contract):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    conversation_id: UUID | None = None
    client_request_id: UUID | None = None
    artifact_id: UUID | None = None
    expected_artifact_revision: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def artifact_target(self):
        if self.artifact_id is not None and self.conversation_id is None:
            raise ValueError("An artifact requires an existing conversation")
        if self.expected_artifact_revision is not None and self.artifact_id is None:
            raise ValueError("An expected revision requires an artifact")
        return self


class SourceMetadata(Contract):
    """Metadata only: never raw documents, excerpts, tool packets or thought signatures."""

    id: Text
    title: Title
    url: str | None = None
    source_file: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    publication_date: str | None = None
    geography: str | None = None
    fetched_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def pages(self):
        if self.page_end is not None and (self.page_start is None or self.page_end < self.page_start):
            raise ValueError("page_end requires an ordered page_start")
        return self


class InnovationMatch(Contract):
    evidence: list[Evidence] = Field(default_factory=list)
    id: Text
    title: Title
    source_url: str | None = None
    video_url: str | None = None
    solution: str = ""
    retrieval_score: float | None = Field(default=None, description="Retrieval ranking, never a fit probability")
    fit_reason: Text
    limitations: list[Text] = Field(default_factory=list)
    sources: list[SourceMetadata] = Field(default_factory=list)


class Artifact(Contract):
    id: UUID
    conversation_id: UUID
    type: ArtifactType
    title: Title
    content_markdown: str = Field(min_length=1)
    revision: int = Field(ge=1, strict=True)
    innovation_id: Text | None = None
    sources: list[SourceMetadata] = Field(default_factory=list)
    updated_at: AwareDatetime


class ArtifactPatch(Contract):
    # Do not strip the user's canonical Markdown, including intentional whitespace.
    content_markdown: str = Field(min_length=1, max_length=ARTIFACT_MAX_CHARS)
    title: Title | None = None
    expected_revision: int = Field(ge=1, strict=True)


class Conversation(Contract):
    id: UUID
    title: Title
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Message(Contract):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    position: int = Field(ge=0)
    turn_id: UUID | None = None  # Greeting has no generation turn.
    status: TurnStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    innovations: list[InnovationMatch] = Field(default_factory=list)
    sources: list[SourceMetadata] = Field(default_factory=list)
    artifact_ids: list[UUID] = Field(default_factory=list)


class ConversationCreated(Contract):
    conversation: Conversation
    messages: list[Message]
    starters: list[Text]


class PaginationQuery(Contract):
    cursor: Annotated[str, StringConstraints(min_length=1, max_length=2048)] | None = None
    limit: int = Field(default=50, ge=1, le=100)


class ConversationList(Contract):
    items: list[Conversation]
    next_cursor: str | None = None


class MessageList(Contract):
    items: list[Message]
    next_cursor: str | None = None


class ArtifactList(Contract):
    items: list[Artifact]


class MatterLink(Contract):
    """A workspace matter saved by a turn (metadata only; content via GET /matters/{id})."""
    id: int = Field(ge=1)
    title: str
    type: Literal["idea_card", "application_draft", "adaptation_plan", "note"]
    status: Literal["draft", "ready", "sent"]
    revision: int = Field(ge=1)


class CreatorStep(Contract):
    key: str
    label: str
    done: bool


class CreatorState(Contract):
    """Guided idea creator progress after a workspace turn."""
    active: bool
    steps: list[CreatorStep] = Field(default_factory=list)
    matter_id: int | None = None


class ChatResponse(Contract):
    answer: str
    innovations: list[InnovationMatch] = Field(default_factory=list)
    conversation_id: UUID
    turn_id: UUID
    message_id: UUID
    artifacts: list[Artifact] = Field(default_factory=list)
    sources: list[SourceMetadata] = Field(default_factory=list)
    matters: list[MatterLink] = Field(default_factory=list)  # Workspace turns only.
    creator: CreatorState | None = None  # Workspace turns only.
    suggestions: list[Text] = Field(default_factory=list, max_length=4)  # Clickable follow-ups; not persisted in chat messages.
    status: Literal["completed", "failed", "interrupted"]


class ErrorResponse(Contract):
    code: ErrorCode
    message: Text  # Polish user copy supplied by the service, never raw exceptions.
    retryable: bool
    turn_id: UUID | None = None
    status: Literal["failed", "interrupted"] | None = None
    current_revision: int | None = Field(default=None, ge=1)
    current_artifact: Artifact | None = None

    @model_validator(mode="after")
    def conflict(self):
        if self.code == "artifact_revision_conflict":
            if self.current_artifact is None or self.current_revision != self.current_artifact.revision:
                raise ValueError("A revision conflict requires the current artifact and revision")
        elif self.current_artifact is not None or self.current_revision is not None:
            raise ValueError("Current artifact is disclosed only for an owned revision conflict")
        return self


class StartedData(Contract):
    conversation_id: UUID
    turn_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID


class ProgressData(Contract):
    turn_id: UUID
    message: Text


class TextDeltaData(Contract):
    message_id: UUID
    delta: str = Field(min_length=1)


class InnovationsData(Contract):
    innovations: list[InnovationMatch]


class SourcesData(Contract):
    sources: list[SourceMetadata]


class StartedEvent(Contract):
    event: Literal["started"] = "started"
    data: StartedData


class ProgressEvent(Contract):
    event: Literal["progress"] = "progress"
    data: ProgressData


class TextDeltaEvent(Contract):
    event: Literal["text_delta"] = "text_delta"
    data: TextDeltaData


class InnovationsEvent(Contract):
    event: Literal["innovations"] = "innovations"
    data: InnovationsData


class SourcesEvent(Contract):
    event: Literal["sources"] = "sources"
    data: SourcesData


class ArtifactUpdatedEvent(Contract):
    event: Literal["artifact_updated"] = "artifact_updated"
    data: Artifact


class CompletedEvent(Contract):
    event: Literal["completed"] = "completed"
    data: ChatResponse

    @model_validator(mode="after")
    def completed(self):
        if self.data.status != "completed":
            raise ValueError("completed requires saved completed output")
        return self


class ErrorEvent(Contract):
    event: Literal["error"] = "error"
    data: ErrorResponse

    @model_validator(mode="after")
    def terminal(self):
        if self.data.turn_id is None or self.data.status is None:
            raise ValueError("A terminal stream error requires persisted turn ID and status")
        return self


StreamEvent = Annotated[
    StartedEvent | ProgressEvent | TextDeltaEvent | InnovationsEvent | SourcesEvent
    | ArtifactUpdatedEvent | CompletedEvent | ErrorEvent,
    Field(discriminator="event"),
]
_event_adapter = TypeAdapter(StreamEvent)


def parse_event(event: str, data: object) -> StreamEvent:
    """Validate a decoded SSE JSON payload using its wire event name."""
    return _event_adapter.validate_python({"event": event, "data": data})


def serialize_event(event: StreamEvent) -> bytes:
    """One UTF-8 SSE frame; JSON escapes embedded newlines inside Markdown/text."""
    validated = _event_adapter.validate_python(event.model_dump())
    return f"event: {validated.event}\ndata: {validated.data.model_dump_json()}\n\n".encode("utf-8")

import datetime as dt
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.conversation import ConversationTagModel
from app.schemas.tagging import Classification
from app.schemas.chat import ChatInnovation
from app.chat.schemas import Artifact, CreatorState, MatterLink, SourceMetadata


class Submission(BaseModel):
    key: UUID
    content: str = Field(min_length=1, max_length=4000)
    model_config = ConfigDict(extra="forbid")

    @field_validator("content")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Message must contain text")
        return value.strip()


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Title must contain text")
        return value.strip()


class Result(BaseModel):
    answer: str
    innovations: list[ChatInnovation] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    sources: list[SourceMetadata] = Field(default_factory=list)
    matters: list[MatterLink] = Field(default_factory=list)
    creator: CreatorState | None = None
    suggestions: list[str] = Field(default_factory=list)
    outcome: Literal["matched", "no_match", "unavailable"]


class OperationModel(BaseModel):
    id: int
    key: str
    user_message_id: int
    assistant_message_id: int | None
    content: str
    status: Literal["processing", "completed", "failed"]
    result: Result | None
    model_config = ConfigDict(from_attributes=True)


class ThreadModel(BaseModel):
    classification: Classification | None = None
    pending: bool = False
    id: int
    title: str | None
    last_activity_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)


class ThreadDetail(ThreadModel):
    tags: list[ConversationTagModel] = Field(default_factory=list)
    operations: list[OperationModel]


class StaffContact(BaseModel):
    name: str
    email: str


class HandoffAttachment(BaseModel):
    id: str
    kind: Literal["artifact", "matter"]
    title: str


class Handoff(BaseModel):
    recipient: str
    subject: str
    body: str
    packet: str
    staff: list[StaffContact] = Field(default_factory=list)
    attachments: list[HandoffAttachment] = Field(default_factory=list)
    mail_delivery: Literal["client", "server"] = "client"


class HandoffSend(BaseModel):
    recipient: EmailStr = Field(max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=50_000)
    artifact_id: str | None = Field(default=None, max_length=64)
    matter_id: int | None = Field(default=None, ge=1)
    include_matters: bool = False
    packet: str = Field(min_length=1, max_length=250000)
    model_config = ConfigDict(extra="forbid")

    @field_validator("subject")
    @classmethod
    def single_line(cls, value):
        if "\r" in value or "\n" in value:
            raise ValueError("Subject must contain a single line")
        return value

    @field_validator("subject", "body", "packet")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Field must contain text")
        return value


class MarkdownPdf(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)
    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "content")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Field must contain text")
        return value.strip()


class HandoffExport(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    packet: str = Field(min_length=1, max_length=250000)
    model_config = ConfigDict(extra="forbid")

import datetime as dt
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.models.matter import MatterStatus, MatterType

#: Same limit as chat artifacts (`ARTIFACT_MAX_CHARS`), so agent edits always fit.
MATTER_MAX_CHARS = 20000


def _strip(value):
    return value.strip() if isinstance(value, str) else value


Title = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=200, examples=["Szkolny czujnik jakości powietrza"])]
# Markdown is stored as written, including intentional whitespace.
Content = Annotated[str, Field(max_length=MATTER_MAX_CHARS, examples=["## Problem\n\nW salach lekcyjnych nikt nie mierzy jakości powietrza."])]


class MatterSummary(BaseModel):
    """List item without the Markdown content."""
    id: int = Field(ge=1, examples=[1])
    title: str
    type: MatterType = Field(examples=[MatterType.application_draft])
    status: MatterStatus = Field(examples=[MatterStatus.draft])
    revision: int = Field(ge=1, examples=[1])
    conversation_id: int | None = Field(default=None, examples=[None])
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class MatterModel(MatterSummary):
    content_markdown: str


class MatterCreate(BaseModel):
    title: Title
    type: MatterType
    content_markdown: Content | None = Field(
        default=None, description="Omitted or empty: the standard section template of the type (empty for `note`).")
    status: MatterStatus = MatterStatus.draft

    model_config = ConfigDict(extra="forbid")


class MatterPatch(BaseModel):
    """Compare-and-swap edit: `expected_revision` must equal the current revision, otherwise 409."""
    expected_revision: int = Field(ge=1, examples=[1])
    title: Title | None = None
    status: MatterStatus | None = None
    content_markdown: Content | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def change(self):
        if self.title is None and self.status is None and self.content_markdown is None:
            raise ValueError("At least one of title, status or content_markdown is required")
        return self


class MatterThread(BaseModel):
    conversation_id: int = Field(ge=1, examples=[1])

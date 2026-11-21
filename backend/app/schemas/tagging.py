"""Persisted classification evidence, without source text or provider diagnostics."""
import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class LabelDecision(BaseModel):
    tag_id: int
    subtag_id: int | None = None
    name: str
    probability: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    selected: bool


class Classification(BaseModel):
    status: Literal["completed", "uncertain", "unavailable", "empty_taxonomy", "no_text"]
    model: str = "fastino/GLiDE"
    version: str = "topic-labels-v1"
    classified_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    decisions: list[LabelDecision] = Field(default_factory=list)
    error_kind: str | None = None
    truncated: bool = False


class AssignedLabel(BaseModel):
    tag_id: int = Field(ge=1)
    subtag_id: int | None = Field(default=None, ge=1)
    source: Literal["ai", "manual"] = "ai"

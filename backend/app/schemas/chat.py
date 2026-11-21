"""Chat payloads shared by the legacy endpoint and persistent workspace."""
from pydantic import BaseModel, Field, field_validator

from app.modules.knowledge import Evidence, RetrievedInnovation

MAX_INNOVATIONS = 3


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must contain text")
        return value.strip()


class ChatInnovation(BaseModel):
    id: str
    title: str
    source_url: str | None = None
    video_url: str | None = None
    solution: str
    summary_url: str | None = None
    retrieval_score: float
    evidence: list[Evidence]
    # Set by the Gemini agent, which explains why a selected innovation fits the user's case.
    fit_reason: str | None = None
    limitations: list[str] = Field(default_factory=list)

    @classmethod
    def from_retrieved(cls, r: RetrievedInnovation) -> "ChatInnovation":
        return cls(
            id=r.innovation.id, title=r.innovation.title, solution=r.innovation.card.solution,
            source_url=r.innovation.source_url, video_url=r.innovation.video_url,
            summary_url=r.summary_document.download_url if r.summary_document else None,
            retrieval_score=r.retrieval_score, evidence=r.evidence,
        )


class ChatResponse(BaseModel):
    answer: str
    innovations: list[ChatInnovation] = Field(
        default_factory=list,
        description="Closest innovations from the knowledge base with source excerpts; empty when retrieval is unavailable",
    )

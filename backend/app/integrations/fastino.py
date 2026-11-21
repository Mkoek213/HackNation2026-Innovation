"""Typed async GLiDE client. See docs/FASTINO.md for the public contract."""

import asyncio
import math
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Annotated, Literal, Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    instructions: str = Field(min_length=1)

    @field_validator("instructions")
    @classmethod
    def require_instructions(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Instructions must contain text")
        return value


class NoulCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    true: str = "Yes"
    false: str = "No"


class NoulQuestion(Question):
    type: Literal["noul"] = "noul"
    criteria: NoulCriteria = Field(default_factory=NoulCriteria)


class ChoiceQuestion(Question):
    type: Literal["choice"] = "choice"
    criteria: dict[str, str] = Field(min_length=2, max_length=255)


class ScoreQuestion(Question):
    type: Literal["score"] = "score"
    criteria: list[str] = Field(min_length=2, max_length=255)


DecisionQuestion = Annotated[
    NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")
]
State = str | dict[str, JsonValue] | list[JsonValue]


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    model: Literal["fastino/GLiDE"] = "fastino/GLiDE"
    state: State
    questions: dict[str, DecisionQuestion] = Field(min_length=1)

    @field_validator("state")
    @classmethod
    def require_state(cls, value: State) -> State:
        if not value or isinstance(value, str) and not value.strip():
            raise ValueError("State must be non-empty")
        return value

    @field_validator("questions")
    @classmethod
    def require_names(cls, value: dict[str, DecisionQuestion]) -> dict[str, DecisionQuestion]:
        if any(not name.strip() for name in value):
            raise ValueError("Question names must contain text")
        return value


Probability = Annotated[float, Field(ge=0, le=1)]


class Answer(BaseModel):
    # Preserve additive provider fields for diagnostic consumers.
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)
    confidence: Probability


class NoulAnswer(Answer):
    type: Literal["noul"]
    noul: Probability


class ChoiceAnswer(Answer):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, Probability]


class ScoreAnswer(Answer):
    type: Literal["score"]
    score: int = Field(ge=0)
    expected_level: float
    probabilities: dict[str, Probability]
    legend: dict[str, str]


DecisionAnswer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    model: str  # versioned names such as "glide_ro27"; informational only
    answers: dict[str, DecisionAnswer]
    usage: TokenUsage

    def validate_against(self, request: DecisionRequest) -> None:
        """Reject missing answers or selections outside the caller's question space."""
        if self.answers.keys() != request.questions.keys():
            raise ValueError("Answer names do not match question names")
        for name, question in request.questions.items():
            answer = self.answers[name]
            if answer.type != question.type:
                raise ValueError("Answer type does not match question type")
            if isinstance(answer, ChoiceAnswer) and isinstance(question, ChoiceQuestion):
                if (
                    answer.probabilities.keys() != question.criteria.keys()
                    or answer.choice not in question.criteria
                ):
                    raise ValueError("Choice answer does not match supplied options")
            if isinstance(answer, ScoreAnswer) and isinstance(question, ScoreQuestion):
                legend = {str(index): level for index, level in enumerate(question.criteria)}
                if answer.legend != legend or answer.probabilities.keys() != legend.keys():
                    raise ValueError("Score answer does not match supplied levels")
                if answer.score >= len(legend) or not 0 <= answer.expected_level <= len(legend) - 1:
                    raise ValueError("Score is outside the supplied scale")
            if isinstance(answer, (ChoiceAnswer, ScoreAnswer)):
                if not math.isclose(sum(answer.probabilities.values()), 1, abs_tol=0.001):
                    raise ValueError("Probabilities do not sum to one")
                winner = answer.choice if isinstance(answer, ChoiceAnswer) else str(answer.score)
                if answer.probabilities[winner] != max(answer.probabilities.values()):
                    raise ValueError("Selected answer is not a most probable outcome")


class FastinoError(Exception):
    """Safe integration error; never includes credentials, state, or provider body."""

    def __init__(self, kind: str, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


def _retry_delay(value: str | None, attempt: int) -> float:
    if value:
        try:
            delay = float(value)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = -1
        if math.isfinite(delay) and delay >= 0:
            return delay
    return 2 ** attempt


class FastinoClient:
    """Reusable client; own one per app lifespan or use an async context manager."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        read_timeout: float = 300,
        connect_timeout: float = 10,
        total_deadline: float = 330,
        max_retries: int = 2,
    ):
        for value in (read_timeout, connect_timeout, total_deadline):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Timeouts and deadline must be finite and positive")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        self._api_key = api_key if api_key is not None else os.getenv("FASTINO_API_KEY")
        self._deadline = total_deadline
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url="https://api.fastino.ai",
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
            follow_redirects=False,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close connection resources after all in-flight decisions finish."""
        await self._http.aclose()

    async def decide(
        self, state: State, questions: dict[str, DecisionQuestion]
    ) -> DecisionResult:
        """Evaluate independent named questions against one shared state."""
        if not self._api_key or not self._api_key.strip():
            raise FastinoError("configuration", "FASTINO_API_KEY is required for inference")
        request = DecisionRequest(state=state, questions=questions)
        try:
            async with asyncio.timeout(self._deadline):
                return await self._send(request)
        except TimeoutError:
            raise FastinoError("deadline", "Fastino decision exceeded its total deadline") from None

    async def _send(self, request: DecisionRequest) -> DecisionResult:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._http.post(
                    "/v1/systemone",
                    headers={"X-API-Key": self._api_key},
                    json=request.model_dump(mode="json"),
                )
            except httpx.TransportError as error:
                if attempt == self._max_retries:
                    kind = "timeout" if isinstance(error, httpx.TimeoutException) else "transport"
                    raise FastinoError(kind, "Fastino transport failed after its retry budget") from None
                await asyncio.sleep(_retry_delay(None, attempt))
                continue
            if response.status_code in (425, 429, 503) and attempt < self._max_retries:
                retry_after = response.headers.get("Retry-After")
                if retry_after is None and response.status_code == 425:
                    retry_after = "60"
                await asyncio.sleep(_retry_delay(retry_after, attempt))
                continue
            if not response.is_success:
                raise FastinoError(
                    "http", "Fastino returned an unsuccessful HTTP status",
                    status_code=response.status_code,
                )
            try:
                result = DecisionResult.model_validate(response.json())
                result.validate_against(request)
                return result
            except (ValidationError, ValueError):
                raise FastinoError("response", "Fastino returned an invalid decision response") from None
        raise RuntimeError("Unreachable retry state")

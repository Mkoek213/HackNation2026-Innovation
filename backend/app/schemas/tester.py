import datetime as dt
from typing import Annotated

from pydantic import BeforeValidator, BaseModel, ConfigDict, Field

from app.schemas.default import ItemList


def _strip_or_none(value):
    """Strips text; a blank value becomes None (the optional field is left out)."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


#: Optional free text: stripped, blank stored as null.
OptionalText = Annotated[str | None, BeforeValidator(_strip_or_none)]


# ============ test sign-ups ============


class TestSignupCreate(BaseModel):
    """`POST /projects/{id}/test-signups`."""

    location_id: int | None = Field(default=None, ge=1, examples=[None], description="Where the tester comes from.")
    message: OptionalText = Field(default=None, max_length=2000, examples=["Chętnie przetestuję w mojej gminie."])

    model_config = ConfigDict(extra="forbid")


class TestSignupModel(BaseModel):
    """A sign-up as its author sees it."""

    id: int = Field(ge=1, examples=[1])
    project_id: int = Field(ge=1, examples=[1])
    user_id: int = Field(ge=1, examples=[1])
    location_id: int | None = Field(default=None, examples=[None])
    message: str | None = Field(default=None, examples=["Chętnie przetestuję w mojej gminie."])
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])

    model_config = ConfigDict(from_attributes=True)


class TestSignupAdminModel(TestSignupModel):
    """A sign-up in the admin listing, with the tester's contact details."""

    username: str = Field(examples=["jan.kowalski"])
    email: str | None = Field(default=None, examples=["jan@example.org"])


# ============ reviews ============


class ReviewInput(BaseModel):
    """`PUT /projects/{id}/reviews/mine`: the whole review, replacing the previous one."""
    rating: int = Field(ge=1, le=5, examples=[5])
    comment: OptionalText = Field(
        default=None, max_length=4000, examples=["Działa dobrze, warto dodać eksport danych do systemu gminy."],
        description="Feedback or proposed improvements.",
    )

    model_config = ConfigDict(extra="forbid")


class ReviewModel(BaseModel):
    id: int = Field(ge=1, examples=[1])
    project_id: int = Field(ge=1, examples=[1])
    user_id: int = Field(ge=1, examples=[1])
    username: str = Field(examples=["jan.kowalski"])
    rating: int = Field(ge=1, le=5, examples=[5])
    comment: str | None = Field(default=None, examples=["Działa dobrze, warto dodać eksport danych do systemu gminy."])
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])
    updated_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])


class ReviewList(ItemList[ReviewModel]):
    """Reviews of one project; `total` is the number of reviews (= ratings)."""
    rating_avg: float | None = Field(examples=[4.5], description="Average rating, 2 decimals; null without reviews.")

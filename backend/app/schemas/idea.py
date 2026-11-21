import datetime as dt
from typing import Annotated

from pydantic import BeforeValidator, BaseModel, ConfigDict, Field

from app.models.idea import IdeaStage, IdeaStatus
from app.utils.schemas_decorators import update_model


def _strip(value):
    return value.strip() if isinstance(value, str) else value


#: Text stripped before the field's length check, so a blank value is rejected.
Stripped = Annotated[str, BeforeValidator(_strip)]


class IdeaModel(BaseModel):
    id: int = Field(ge=1, examples=[1])
    author_id: int = Field(ge=1, examples=[1])
    title: str = Field(examples=["Sąsiedzka wymiana umiejętności"])
    essence: str = Field(examples=["Uczniowie technikum budują czujniki jakości powietrza, a dane trafiają do szkolnej platformy."])
    target_group: str = Field(examples=["Szkoły podstawowe i gminy"])
    stage: IdeaStage = Field(examples=[IdeaStage.idea])
    tag_id: int | None = Field(default=None, examples=[1])
    location_id: int | None = Field(default=None, examples=[None])
    status: IdeaStatus = Field(examples=[IdeaStatus.submitted])
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])

    model_config = ConfigDict(from_attributes=True)


class IdeaCreate(BaseModel):
    title: Stripped = Field(min_length=1, max_length=200, examples=["Sąsiedzka wymiana umiejętności"])
    essence: Stripped = Field(min_length=1, max_length=8000, examples=["Uczniowie technikum budują czujniki jakości powietrza, a dane trafiają do szkolnej platformy."])
    target_group: Stripped = Field(min_length=1, max_length=2000, examples=["Szkoły podstawowe i gminy"])
    stage: IdeaStage = Field(examples=[IdeaStage.idea])
    tag_id: int | None = Field(default=None, ge=1, examples=[None])
    location_id: int | None = Field(default=None, ge=1, examples=[None])

    model_config = ConfigDict(extra="forbid")


@update_model(nullable=("tag_id", "location_id"))
class IdeaUpdate(IdeaCreate):
    """
    All fields optional. `tag_id` and `location_id` can be cleared with null.
    The author may change the content fields while the idea is `submitted`; only the admin may set `status`.
    """
    status: IdeaStatus = Field(examples=[IdeaStatus.published])

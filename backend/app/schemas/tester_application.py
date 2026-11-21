import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.tester_application import ApplicationSource, ApplicationStatus
from app.modules.knowledge.schemas import INNOVATION_ID_PATTERN
from app.schemas.tester import OptionalText
from app.schemas.volunteer import VolunteerLabel

#: Knowledge innovation id (slug), as in `api/v1/knowledge/innovations/{innovation_id}`.
InnovationSlug = Annotated[str, Field(pattern=INNOVATION_ID_PATTERN, max_length=120, examples=["uprp-p-441234"])]


class TesterApplicationCreate(BaseModel):
    """`POST /tester-applications`."""

    innovation_id: InnovationSlug
    message: OptionalText = Field(default=None, max_length=2000, examples=["Opiekuję się mamą, chętnie sprawdzę."])

    model_config = ConfigDict(extra="forbid")


class TesterApplicationDecision(BaseModel):
    """`PATCH /tester-applications/{id}`."""

    status: Literal["approved", "rejected"]

    model_config = ConfigDict(extra="forbid")


class TesterApplicationAssign(BaseModel):
    """`POST /tester-applications/assign`: an admin adds a pool tester directly as approved."""

    user_id: int = Field(ge=1, examples=[1])
    innovation_id: InnovationSlug

    model_config = ConfigDict(extra="forbid")


class TesterApplicationModel(BaseModel):
    """An application as its tester sees it; the title falls back to the slug when the innovation is gone."""

    id: int
    innovation_id: str
    innovation_title: str
    status: ApplicationStatus
    source: ApplicationSource
    message: str | None
    decided_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


class TesterApplicationAdminModel(TesterApplicationModel):
    """An application with the tester's contact details and tags, for admins only."""

    user_id: int
    email: str
    phone: str
    roles: list[str]
    interests: list[str]
    tags: list[VolunteerLabel]

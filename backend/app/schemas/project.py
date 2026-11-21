import datetime as dt
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, WithJsonSchema, computed_field

from app.models.location import LocationKind
from app.models.project import ProjectStatus
from app.schemas.tag import Name
from app.utils.schemas_decorators import update_model

_http_url = TypeAdapter(HttpUrl)

#: An http(s) URL, validated (and normalized) by HttpUrl but kept as a plain string.
Url = Annotated[
    str,
    AfterValidator(lambda value: str(_http_url.validate_python(value))),
    WithJsonSchema({"type": "string", "format": "uri", "minLength": 1, "maxLength": 2083}),
]


class ProjectModel(BaseModel):
    """A project in lists (without the full description)."""
    id: int = Field(ge=1, examples=[1])
    title: str = Field(examples=["Spółdzielnia sąsiedzka"])
    summary: str = Field(examples=["Uczniowie budują czujniki jakości powietrza dla szkół."])
    website_url: str | None = Field(default=None, examples=["https://example.org/projekt"])
    video_url: str | None = Field(default=None, examples=[None])
    tag_id: int = Field(ge=1, examples=[1])
    subtag_id: int | None = Field(default=None, examples=[None])
    location_id: int | None = Field(default=None, examples=[None])
    latitude: float | None = Field(default=None, examples=[50.06])
    longitude: float | None = Field(default=None, examples=[19.94])
    status: ProjectStatus = Field(examples=[ProjectStatus.published])
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])
    updated_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])

    model_config = ConfigDict(from_attributes=True)


class ProjectDocumentModel(BaseModel):
    """A PDF attached to a project. `url` opens it (API path, relative to the backend)."""
    id: int = Field(ge=1, examples=[1])
    project_id: int = Field(ge=1, examples=[1])
    title: str = Field(examples=["Raport z pilotażu"])
    size_bytes: int = Field(ge=0, examples=[123456])
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])

    model_config = ConfigDict(from_attributes=True)

    @computed_field(examples=["/projects/1/documents/1"])
    @property
    def url(self) -> str:
        return f"/projects/{self.project_id}/documents/{self.id}"


class ProjectDetail(ProjectModel):
    """A project with its description, PDFs, and participants total."""
    description: str = Field(examples=["## Opis\nPełny opis projektu."])
    documents: list[ProjectDocumentModel] = Field(default_factory=list)
    participants_total: int = Field(ge=0, examples=[120])


class ProjectCreate(BaseModel):
    """A new project, always created as `draft`."""
    title: Name = Field(min_length=1, max_length=200, examples=["Spółdzielnia sąsiedzka"])
    summary: str = Field(min_length=1, max_length=2000, examples=["Uczniowie budują czujniki jakości powietrza dla szkół."])
    description: str = Field(default="", max_length=50000, examples=["## Opis\nPełny opis projektu."])
    website_url: Url | None = Field(default=None, examples=["https://example.org/projekt"])
    video_url: Url | None = Field(default=None, examples=[None])
    tag_id: int = Field(ge=1, examples=[1])
    subtag_id: int | None = Field(default=None, ge=1, examples=[None])
    location_id: int | None = Field(default=None, ge=1, examples=[None])
    latitude: float | None = Field(default=None, ge=-90, le=90, examples=[50.06])
    longitude: float | None = Field(default=None, ge=-180, le=180, examples=[19.94])

    model_config = ConfigDict(extra="forbid")


class _ProjectEditable(ProjectCreate):
    status: ProjectStatus = Field(examples=[ProjectStatus.published])


@update_model(nullable=("website_url", "video_url", "subtag_id", "location_id", "latitude", "longitude"))
class ProjectUpdate(_ProjectEditable):
    """All fields optional. `{"status": "published"}` publishes the project.
    Links, subtag, location and coordinates can be cleared with null."""
    pass


class ProjectProperties(BaseModel):
    """`properties` of a feature in `/projects/geojson`."""
    id: int = Field(ge=1, examples=[1])
    title: str = Field(examples=["Spółdzielnia sąsiedzka"])
    tag_id: int = Field(ge=1, examples=[1])
    subtag_id: int | None = Field(default=None, examples=[None])

    model_config = ConfigDict(from_attributes=True)


# ============ participants ============


class ParticipantInput(BaseModel):
    """One row of `PUT /projects/{id}/participants`; `location_id: null` = unknown origin."""
    location_id: int | None = Field(default=None, ge=1, examples=[1])
    participants_count: int = Field(ge=0, le=10_000_000, examples=[25])

    model_config = ConfigDict(extra="forbid")


class ParticipantModel(BaseModel):
    """A stored participants row."""
    id: int = Field(ge=1, examples=[1])
    project_id: int = Field(ge=1, examples=[1])
    location_id: int | None = Field(default=None, examples=[1])
    participants_count: int = Field(ge=0, examples=[25])

    model_config = ConfigDict(from_attributes=True)


class ParticipantsByLocation(BaseModel):
    """Participants from one location; all location fields are null for the unknown origin."""
    location_id: int | None = Field(examples=[1])
    name: str | None = Field(examples=["Rzeszów"])
    teryt_code: str | None = Field(examples=["1863011"])
    kind: LocationKind | None = Field(examples=[LocationKind.municipality])
    count: int = Field(ge=0, examples=[25])


class ParticipantsSummary(BaseModel):
    total: int = Field(ge=0, examples=[25])
    by_location: list[ParticipantsByLocation]


class ParticipantProperties(BaseModel):
    """`properties` of a feature in `/projects/{id}/participants?format=geojson`."""
    id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Rzeszów"])
    teryt_code: str = Field(examples=["1863011"])
    kind: LocationKind = Field(examples=[LocationKind.municipality])
    count: int = Field(ge=0, examples=[25])

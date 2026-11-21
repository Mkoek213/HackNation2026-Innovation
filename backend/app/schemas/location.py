from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.location import LocationKind
from app.schemas.geojson import Geometry

#: TERYT TERC code length per kind (the municipality code includes its type digit).
TERYT_CODE_LENGTH = {
    LocationKind.voivodeship: 2,
    LocationKind.county: 4,
    LocationKind.municipality: 7,
}


class LocationModel(BaseModel):
    """A location without its boundary geometry (see `/locations/geojson` for that)."""
    id: int = Field(ge=1, examples=[1])
    teryt_code: str = Field(examples=["1863011"])
    name: str = Field(examples=["Rzeszów"])
    kind: LocationKind = Field(examples=[LocationKind.municipality])
    parent_id: int | None = Field(default=None, examples=[2])
    osm_relation_id: int | None = Field(default=None, examples=[None])
    latitude: float = Field(examples=[50.06])
    longitude: float = Field(examples=[19.94])

    model_config = ConfigDict(from_attributes=True)


class LocationProperties(BaseModel):
    """`properties` of a feature in `/locations/geojson`."""
    id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Rzeszów"])
    teryt_code: str = Field(examples=["1863011"])
    kind: LocationKind = Field(examples=[LocationKind.municipality])

    model_config = ConfigDict(from_attributes=True)


class LocationImport(BaseModel):
    """One location read from a GeoJSON import file (`scripts/seed_locations.py`).
    The parent is not given: it is derived from the TERYT code prefix."""
    teryt_code: str = Field(pattern=r"^(\d{2}|\d{4}|\d{7})$", examples=["1863011"])
    name: str = Field(min_length=1, examples=["Rzeszów"])
    kind: LocationKind = Field(examples=[LocationKind.municipality])
    osm_relation_id: int | None = Field(default=None, examples=[None])
    latitude: float = Field(ge=-90, le=90, examples=[50.06])
    longitude: float = Field(ge=-180, le=180, examples=[19.94])
    boundary: Geometry | None = Field(default=None, examples=[None])

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _kind_matches_code(self):
        if len(self.teryt_code) != TERYT_CODE_LENGTH[self.kind]:
            raise ValueError(f"A {self.kind} needs a {TERYT_CODE_LENGTH[self.kind]}-digit TERYT code.")
        return self

    @property
    def parent_teryt_code(self) -> str | None:
        """gmina `1261011` -> powiat `1261` -> voivodeship `12` -> None."""
        return {7: self.teryt_code[:4], 4: self.teryt_code[:2]}.get(len(self.teryt_code))

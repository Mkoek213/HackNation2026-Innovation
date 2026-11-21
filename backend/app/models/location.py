import datetime as dt
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, Double, Enum, ForeignKey, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column, Mapped

from app.database.database import Base, BigIntPK


class LocationKind(StrEnum):
    voivodeship = "voivodeship"
    county = "county"  # powiat
    municipality = "municipality"  # gmina


#: GeoJSON geometry column: jsonb on PostgreSQL, JSON (text) on SQLite.
GeoJSONType = JSON().with_variant(JSONB(), "postgresql")


class Location(Base):
    """
    Podkarpackie administrative units (gmina -> powiat -> voivodeship), linked to
    OpenStreetMap boundary relations so the frontend can draw them on an OSM map.
    """
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    # Official TERYT TERC code (`teryt:terc` in OSM): 2 digits voivodeship,
    # 4 digits county, 7 digits municipality. Parents are derived from its prefix.
    teryt_code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column()
    kind: Mapped[LocationKind] = mapped_column(
        Enum(LocationKind, name="location_kind", native_enum=False, length=16, create_constraint=True),
        index=True,
    )
    parent_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("locations.id"), index=True, default=None)
    osm_relation_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # Centroid, for markers and map.setView().
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    # Simplified GeoJSON geometry (Polygon/MultiPolygon).
    boundary: Mapped[dict[str, Any] | None] = mapped_column(GeoJSONType, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

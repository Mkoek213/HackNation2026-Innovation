"""
GeoJSON (RFC 7946) response models. They serialize to plain GeoJSON, so the
frontend passes them straight to Leaflet `L.geoJSON(data)` or a MapLibre
`geojson` source without conversion. Coordinates are `[longitude, latitude]`.
"""
from numbers import Real
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, Field

P = TypeVar("P")

#: Nesting depth of `coordinates` per geometry type (1 = a single position).
_COORDINATE_DEPTH = {
    "Point": 1,
    "MultiPoint": 2,
    "LineString": 2,
    "MultiLineString": 3,
    "Polygon": 3,
    "MultiPolygon": 4,
}


def _check_position(position: Any) -> None:
    if (
            not isinstance(position, list)
            or not 2 <= len(position) <= 3
            or not all(isinstance(c, Real) and not isinstance(c, bool) for c in position)
    ):
        raise ValueError(f"A position must be [longitude, latitude], got {position!r}.")
    lon, lat = position[0], position[1]
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(f"Position {position!r} is out of range; GeoJSON uses [longitude, latitude].")


def _check_coordinates(coordinates: Any, depth: int) -> None:
    if depth == 1:
        _check_position(coordinates)
        return
    if not isinstance(coordinates, list):
        raise ValueError("Geometry coordinates are nested too shallowly.")
    for item in coordinates:
        _check_coordinates(item, depth - 1)


def _check_ring(ring: list) -> None:
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("A polygon ring needs at least 4 positions and must be closed (first == last).")


def validate_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    """Checks the shape of a GeoJSON geometry object: type, coordinate nesting,
    `[longitude, latitude]` ranges and closed polygon rings."""
    kind = geometry.get("type")
    if kind == "GeometryCollection":
        members = geometry.get("geometries")
        if not isinstance(members, list):
            raise ValueError("A GeometryCollection needs a `geometries` list.")
        for member in members:
            validate_geometry(member)
        return geometry
    if kind not in _COORDINATE_DEPTH:
        raise ValueError(f"Unknown GeoJSON geometry type {kind!r}.")
    coordinates = geometry.get("coordinates")
    _check_coordinates(coordinates, _COORDINATE_DEPTH[kind])
    if kind == "Polygon":
        for ring in coordinates:
            _check_ring(ring)
    elif kind == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                _check_ring(ring)
    return geometry


#: A validated GeoJSON geometry object, kept as a plain dict.
Geometry = Annotated[dict[str, Any], AfterValidator(validate_geometry)]


def point(longitude: float, latitude: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [longitude, latitude]}


class Feature(BaseModel, Generic[P]):
    type: Literal["Feature"] = "Feature"
    geometry: Geometry | None = Field(examples=[point(19.94, 50.06)])
    properties: P


class FeatureCollection(BaseModel, Generic[P]):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature[P]]

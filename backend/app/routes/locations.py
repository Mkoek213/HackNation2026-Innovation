from fastapi import APIRouter, Path, Query, status

from app.dependencies import DatabaseDep, PaginationDep
from app.docs import Tags
from app.models import LocationKind
from app.repos.location_repo import LocationRepo
from app.schemas.default import ItemList, NOT_FOUND
from app.schemas.geojson import FeatureCollection
from app.schemas.location import LocationModel, LocationProperties

router = APIRouter(
    prefix="/locations",
    tags=[Tags.Locations],
    responses={},
)


@router.get("",
            dependencies=None,
            response_model=ItemList[LocationModel],
            status_code=status.HTTP_200_OK,
            summary="Get locations",
            response_description="Successful Response")
async def get_locations(
        db: DatabaseDep,
        page: PaginationDep,
        kind: LocationKind | None = Query(None, description="Only this kind of administrative unit."),
        parent_id: int | None = Query(None, ge=1, description="Only direct children of this location."),
        q: str | None = Query(None, min_length=1, max_length=100, description="Name fragment or TERYT code prefix."),
):
    """
    Get locations for pickers, ordered by name, without boundary geometry. Public. \\
    Paginated with `?limit=&offset=` (`total` is the unpaginated count).
    """
    return await LocationRepo(db).search(
        kind=kind, parent_id=parent_id, q=q, limit=page.limit, offset=page.offset,
    )


@router.get("/geojson",
            dependencies=None,
            response_model=FeatureCollection[LocationProperties],
            status_code=status.HTTP_200_OK,
            summary="Get locations as GeoJSON",
            response_description="GeoJSON FeatureCollection")
async def get_locations_geojson(
        db: DatabaseDep,
        kind: LocationKind | None = Query(None, description="Only this kind of administrative unit."),
        parent_id: int | None = Query(None, ge=1, description="Only direct children of this location."),
):
    """
    Get locations as a GeoJSON `FeatureCollection` for Leaflet `L.geoJSON(data)` or a MapLibre source. Public. \\
    Each feature's `geometry` is the simplified boundary (the centroid `Point` when no boundary is stored);
    `properties` are `{id, name, teryt_code, kind}`. Not paginated.
    """
    return await LocationRepo(db).geojson(kind=kind, parent_id=parent_id)


@router.get("/{location_id}",
            dependencies=None,
            response_model=LocationModel,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get location one",
            response_description="Successful Response")
async def get_location_one(
        db: DatabaseDep,
        location_id: int = Path(ge=1),
):
    """
    Get one location with its centroid and `osm_relation_id`. Public. \\
    Raises 404 Not Found when it does not exist.
    """
    return await LocationRepo(db).get_one(id=location_id, key_loc="path")

"""
Upserts locations from a GeoJSON FeatureCollection into the `locations` table,
keyed by `teryt_code` (idempotent: re-running changes nothing). Run from
backend/ or inside the container, after `alembic upgrade head`:

    python scripts/seed_locations.py [path/to/file.geojson]

Defaults to data/locations_podkarpackie.geojson. Each feature's `properties` are
`{teryt_code, name, kind, osm_relation_id?, latitude, longitude}`; a Polygon or
MultiPolygon `geometry` is stored as the boundary. Parents are derived from the
TERYT prefix and must be in the file or already in the database.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.database import sessionmanager  # noqa: E402
from app.repos.location_repo import ImportResult, LocationRepo  # noqa: E402
from app.schemas.location import LocationImport  # noqa: E402

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "locations_podkarpackie.geojson"
BOUNDARY_TYPES = {"Polygon", "MultiPolygon"}


def read_locations(data: dict[str, Any]) -> list[LocationImport]:
    """Turns a GeoJSON FeatureCollection into validated import rows."""
    if data.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection.")
    items = []
    for feature in data["features"]:
        geometry = feature.get("geometry")
        boundary = geometry if geometry and geometry.get("type") in BOUNDARY_TYPES else None
        items.append(LocationImport(**feature["properties"], boundary=boundary))
    return items


async def seed(path: Path) -> ImportResult:
    items = read_locations(json.loads(path.read_text(encoding="utf-8")))
    await sessionmanager.init_db()
    try:
        # SQLite has no migrations (see app.lifespan); create its tables here too.
        if sessionmanager.dialect_name == "sqlite":
            await sessionmanager.create_db()
        async with sessionmanager.session_maker() as db:
            return await LocationRepo(db).import_locations(items)
    finally:
        await sessionmanager.close()


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    result = asyncio.run(seed(path))
    print(f"{path.name}: {result.created} created, {result.updated} updated, {result.unchanged} unchanged.")


if __name__ == "__main__":
    main()

"""
Imports the Podkarpackie administrative hierarchy (voivodeship, powiats, gminas)
from OpenStreetMap into a GeoJSON file, then upserts it into `locations` with
`scripts/seed_locations.py`. Run from backend/ (needs the dev dependencies):

    uv run python scripts/import_osm_locations.py [options]

One run makes one Overpass API request (about 20 MB, up to a few minutes). Use
`--save-raw` to keep the response and `--from-raw` to rebuild the file offline.
Seeding uses `DATABASE_URL`, like the app. `--no-seed` only writes the file;
seed it later with `scripts/seed_locations.py data/locations_podkarpackie.geojson`.

Source: `boundary=administrative` relations with `teryt:terc` 18… at OSM
`admin_level` 4 (voivodeship), 6 (powiat, incl. cities with powiat rights) and
7 (gmina). Boundaries are simplified as a coverage per level, so neighbours keep
shared borders without gaps or overlaps. The point is the centroid, or a point
inside the area when the centroid falls outside it (e.g. a powiat around a city).
"""
import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import shapely
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize_full, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seed_locations import read_locations, seed  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_OUTPUT = DATA_DIR / "locations_podkarpackie.geojson"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "radar-innowacji-locations-import/1.0 (one-off seed script)"

#: OSM admin_level -> (`locations.kind`, TERYT code length).
LEVELS = {"4": ("voivodeship", 2), "6": ("county", 4), "7": ("municipality", 7)}
#: Official counts for Podkarpackie, printed next to the actual ones for comparison.
EXPECTED = {"voivodeship": 1, "county": 25, "municipality": 160}

QUERY = """
[out:json][timeout:300];
area["boundary"="administrative"]["admin_level"="4"]["teryt:terc"="18"]->.region;
rel(area.region)["boundary"="administrative"]["admin_level"~"^(4|6|7)$"]["teryt:terc"~"^18"];
out geom;
"""


def fetch(url: str) -> dict[str, Any]:
    print(f"Querying {url} (this can take a few minutes)…", file=sys.stderr)
    response = httpx.post(url, data={"data": QUERY}, headers={"User-Agent": USER_AGENT}, timeout=400)
    response.raise_for_status()
    return response.json()


def build_area(relation: dict[str, Any]) -> tuple[Polygon | MultiPolygon, list[str]]:
    """Assembles a relation's `outer`/`inner` member ways into one area.
    Returns the geometry and a list of problems (unclosed rings, empty result)."""
    lines: dict[str, list[LineString]] = {"outer": [], "inner": []}
    for member in relation.get("members", []):
        if member["type"] != "way" or len(member.get("geometry") or []) < 2:
            continue
        role = "inner" if member.get("role") == "inner" else "outer"
        lines[role].append(LineString([(p["lon"], p["lat"]) for p in member["geometry"]]))

    problems = []
    parts = {}
    for role, role_lines in lines.items():
        # unary_union nodes the ways, so rings split over several ways close up.
        polygons, cuts, dangles, invalid = polygonize_full(unary_union(role_lines)) if role_lines else ([], [], [], [])
        if role_lines and (not shapely.is_empty(dangles) or not shapely.is_empty(invalid)):
            problems.append(f"unclosed {role} ring(s)")
        parts[role] = unary_union(list(polygons.geoms)) if role_lines else Polygon()

    area = shapely.make_valid(parts["outer"].difference(parts["inner"]))
    area = unary_union([g for g in getattr(area, "geoms", [area]) if isinstance(g, (Polygon, MultiPolygon))])
    if area.is_empty:
        problems.append("no area could be built")
    return area, problems


def inner_point(area: Polygon | MultiPolygon) -> tuple[float, float]:
    centroid = area.centroid
    point = centroid if area.contains(centroid) else area.representative_point()
    return round(point.x, 5), round(point.y, 5)


def build_features(raw: dict[str, Any], tolerance: float) -> tuple[list[dict[str, Any]], list[str]]:
    rows, problems = [], []
    for relation in raw["elements"]:
        if relation.get("type") != "relation":
            continue
        tags = relation.get("tags", {})
        code, level = tags.get("teryt:terc", ""), tags.get("admin_level")
        if level not in LEVELS or len(code) != LEVELS[level][1]:
            problems.append(f"relation {relation['id']} ({tags.get('name')}): skipped, "
                            f"admin_level {level} with TERYT {code!r}")
            continue
        area, area_problems = build_area(relation)
        problems += [f"{code} {tags.get('name')} (relation {relation['id']}): {p}" for p in area_problems]
        rows.append(dict(relation=relation, code=code, kind=LEVELS[level][0], name=tags.get("name", code), area=area))

    # Simplify each level as one coverage, so shared borders stay shared.
    for kind, _ in LEVELS.values():
        level_rows = [r for r in rows if r["kind"] == kind and not r["area"].is_empty]
        if not level_rows:
            continue
        simplified = shapely.coverage_simplify([r["area"] for r in level_rows], tolerance)
        for row, geometry in zip(level_rows, simplified):
            row["boundary"] = shapely.make_valid(shapely.set_precision(geometry, 1e-5))

    features = []
    for row in sorted(rows, key=lambda r: r["code"]):
        if row["area"].is_empty:
            longitude = latitude = None
            geometry = None
        else:
            longitude, latitude = inner_point(row["area"])
            geometry = json.loads(shapely.to_geojson(row["boundary"]))
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "teryt_code": row["code"],
                "name": row["name"],
                "kind": row["kind"],
                "osm_relation_id": row["relation"]["id"],
                "latitude": latitude,
                "longitude": longitude,
            },
        })
    return features, problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="GeoJSON file to write")
    parser.add_argument("--tolerance", type=float, default=0.002,
                        help="coverage simplification tolerance in degrees (default 0.002, about 150-220 m)")
    parser.add_argument("--overpass-url", default=OVERPASS_URL)
    parser.add_argument("--save-raw", type=Path, help="also save the raw Overpass response here")
    parser.add_argument("--from-raw", type=Path, help="read a saved Overpass response instead of querying")
    parser.add_argument("--no-seed", action="store_true", help="only write the file, do not upsert into the database")
    args = parser.parse_args()

    if args.from_raw:
        raw = json.loads(args.from_raw.read_text(encoding="utf-8"))
    else:
        raw = fetch(args.overpass_url)
        if args.save_raw:
            args.save_raw.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    osm_date = raw.get("osm3s", {}).get("timestamp_osm_base", date.today().isoformat())

    features, problems = build_features(raw, args.tolerance)
    for problem in problems:
        print(f"WARNING: {problem}", file=sys.stderr)
    usable = [f for f in features if f["geometry"] is not None]

    collection = {
        "type": "FeatureCollection",
        "description": (
            f"Podkarpackie administrative boundaries from OpenStreetMap (data as of {osm_date}), "
            f"simplified with tolerance {args.tolerance}°. Generated by scripts/import_osm_locations.py. "
            "© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)."
        ),
        "features": usable,
    }
    read_locations(collection)  # Validates every feature like the seed script will.
    args.output.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    counts = Counter(f["properties"]["kind"] for f in usable)
    size_kb = args.output.stat().st_size / 1024
    print(f"Wrote {args.output.name}: {len(usable)} features, {size_kb:.0f} KB.")
    for kind, expected in EXPECTED.items():
        print(f"  {kind}: {counts[kind]} (official: {expected})")
    if len(usable) < len(features):
        print(f"  skipped without geometry: {len(features) - len(usable)}")

    if not args.no_seed:
        result = asyncio.run(seed(args.output))
        print(f"Seeded: {result.created} created, {result.updated} updated, {result.unchanged} unchanged.")


if __name__ == "__main__":
    main()

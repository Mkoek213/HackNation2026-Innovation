# Radar innowacji API

FastAPI backend `app.main:app`: SQLAlchemy 2 async persistence with Alembic migrations, JWT login (cookie or Bearer)
with `admin`/`user` roles and self-registration, and the Radar API: locations and GeoJSON for OpenStreetMap maps,
admin-defined tags/subtags, projects with PDFs and participants, persisted conversations with automatic tagging and
project matches (public chat, saved history after login), ideas, visit tracking and admin
statistics. The legacy `POST /chat` stays for the current frontend. The implemented endpoints and tables are in
[API.md](API.md) and [DATABASE.md](DATABASE.md).

## Setup and run

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.13. From `backend/`:

```bash
uv sync --locked
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Settings come from environment variables (`app/config.py`). Copy the repository root `.env.example` to `.env`;
Compose supplies it to the container, and a direct run uses `uv run --env-file ../.env uvicorn ...`
(override the Compose-only `DATABASE_URL` hostname, see the [development guide](../docs/DEVELOPMENT.md)).
Without `DATABASE_URL` the app uses SQLite (`test.db`) and creates the tables at startup.
Interactive docs: `http://127.0.0.1:8000/docs.html`; schema: `/openapi.json`.

## Migrations (PostgreSQL)

Alembic manages the PostgreSQL schema (`alembic.ini`, `migrations/`). The app never runs `create_all` on PostgreSQL;
the Docker entrypoint runs `alembic upgrade head` before Uvicorn.

```bash
export DATABASE_URL=postgresql+asyncpg://radar:radar@localhost:5432/radar   # e.g. `docker compose up -d db`
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic revision --autogenerate -m "add projects"   # after changing models; review the result
uv run alembic check                                        # models and migrations agree
```

A database created by an older build with `create_all` already has a `users` table without `email`. Recreate it
(`docker compose down -v`) before the first migration.

## Locations (map data)

`data/locations_podkarpackie.geojson` holds the full Podkarpackie hierarchy from OpenStreetMap (1 voivodeship,
25 powiats, 160 gminas) with simplified boundaries, upserted by TERYT code (re-running is safe):

```bash
uv run python scripts/seed_locations.py   # default file: data/locations_podkarpackie.geojson
```

To regenerate the OSM file (one Overpass API request; needs the dev dependencies for `shapely`):

```bash
uv run python scripts/import_osm_locations.py --save-raw overpass.json   # writes the file and seeds the database
uv run python scripts/import_osm_locations.py --from-raw overpass.json --no-seed --tolerance 0.001   # offline rebuild
```

The data is © OpenStreetMap contributors under the ODbL; a map showing it must credit OpenStreetMap.

## Demo data

`scripts/seed_demo.py` fills an empty database with synthetic demo data from `data/demo/demo.json`: the Podkarpackie
locations, 7 topics with subtopics, 12 demo users, 6 published projects (real records of the
[Interreg 2021-2027 project list](https://interreg.gov.pl/lista-projektow/), each with a generated PDF card and invented
participant counts), ideas, and a 60-day history of conversations and visits
for the statistics. Run it after the migrations; it is idempotent:

```bash
docker compose exec backend python scripts/seed_demo.py
uv run --env-file ../.env python scripts/seed_demo.py   # host run; override DATABASE_URL and S3_ENDPOINT_URL
```

Demo users (`demo.anna`, `demo.ngo`, ...) log in with `DEMO_USER_PASSWORD` (default `demo-haslo-2026`); the admin
comes from `ADMIN_USERNAME`/`ADMIN_PASSWORD`. Rows are matched by natural keys, so a second run adds nothing and keeps
admin edits. The history is generated once, relative to the day of the first run. Without S3 configured, the PDFs
are skipped; run the script again once storage is available.

## Compose stack

From the repository root, with `.env` copied from `.env.example`:

```bash
docker compose up --build -d                       # the backend entrypoint runs `alembic upgrade head`
docker compose exec backend python scripts/seed_demo.py
docker compose ps                                   # backend "healthy" (Docker HEALTHCHECK on GET /healthcheck)
```

## Knowledge base and Fastino client

The Qdrant knowledge base lives in `app/modules/knowledge/` and is mounted in `app.main` under
`/api/v1/knowledge`; see its [README](app/modules/knowledge/README.md). Import `FastinoClient` and typed
questions from `app.integrations.fastino`; the [interface guide](../docs/FASTINO.md) documents arguments,
results, errors, configuration, lifetime, and examples. Set `FASTINO_API_KEY` in the root `.env` before
inference. The client is currently unused. Chat uses knowledge retrieval and does not call GLiDE.

## Shared building blocks

- `CRUDRepo` (`app/utils/crud_repo.py`): one repository per model; `get_all(limit=, offset=, **filters)`.
- `PaginationDep` (`app/dependencies.py`): `?limit=` (default 20, max 100) and `?offset=` for list endpoints.
- `VisitorDep` (`app/utils/auth.py`): `Actor(user | None, visitor_id)` for public endpoints; sets the anonymous
  `visitor_id` cookie when missing.
- `assert_owner(actor, user_id, visitor_id)`: owner check for user- or visitor-owned rows; admins always pass.

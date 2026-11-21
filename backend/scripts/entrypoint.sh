#!/bin/sh
set -e

# Bring the database schema up to date before serving (DATABASE_URL from the environment).
alembic upgrade head

# Podkarpackie boundaries (idempotent upsert by TERYT code, ~1 s). Without this the
# locations table stays empty on a fresh database and /locations/geojson returns no features.
python scripts/seed_locations.py data/locations_podkarpackie.geojson

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --log-config /code/config/log.yaml

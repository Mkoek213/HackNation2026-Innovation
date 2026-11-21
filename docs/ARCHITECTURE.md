# Repository Architecture

## Stack

| Area | Implementation |
| --- | --- |
| Frontend | Next.js App Router, React, TypeScript, Tailwind CSS, Polish UI (`frontend/`) |
| Backend | One Python 3.13 FastAPI app `app.main:app`, SQLAlchemy 2 async, Pydantic 2 (`backend/`) |
| Persistence | PostgreSQL in Compose, schema by Alembic (single initial revision `0001`); SQLite with `create_all` for quick local runs |
| Identity | Argon2 passwords, JWT in an HttpOnly cookie with CSRF, roles `admin`/`user`; anonymous `visitor_id` cookie |
| Knowledge base | `backend/app/modules/knowledge/`: PDF/DOCX/ZIP ingestion, Gemini embeddings plus BM25 in Qdrant, documents in S3-compatible storage, `/api/v1/knowledge` |
| Chat | `backend/app/chat/`: Gemini tool-calling agent with retrieval, live source reading, case facts, documents, matters and the submission creator; answers pass a quotation-checked review step |
| Classification | Fastino GLiDE for sectors of uploaded documents and conversation topics (`backend/app/integrations/fastino.py`, `backend/app/services/tagging.py`) |
| Deployment | Docker Compose locally, including Qdrant with its own persistent volume; Google Cloud Run via `deploy/gcp/deploy.ps1` (not provisioned yet) |

## Source map

| Path | Responsibility |
| --- | --- |
| `frontend/app/` | Thin routes: `/` home, `/rozmowa` chat, `/matters` Moje sprawy, `/knowledge/innovations` innovation base, `/tester` pilot sign-up, `/contact`, `/administration/*` admin views |
| `frontend/features/<id>/` | Feature UI behind a public `index.ts`: `home`, `workspace` (chat), `matters`, `knowledge`, `tester` (pilot partners), `administration`, `contact` |
| `frontend/app/api/backend/[...path]/route.ts` | Allowlisted same-origin proxy to FastAPI (cookies and CSRF) |
| `frontend/components/` | Site header, accessibility bar, shared UI primitives and icons |
| `backend/app/main.py`, `config.py`, `lifespan.py` | App composition, settings from the root `.env`, startup |
| `backend/app/models/`, `schemas/`, `repos/`, `routes/` | One model, schema module, repo and router per resource |
| `backend/app/routes/operator.py` | PCI staff contacts and the Markdown to PDF helper |
| `backend/app/modules/knowledge/taxonomy.py` | Sectors, innovation types, institution types and maturity stages with Polish labels |
| `backend/app/modules/tester_tags.py` | Pilot partner types and sector interests (the pool is stored as "volunteers"/"testers" internally) |
| `backend/app/chat/sources.py` | Live reading of approved public pages (Interreg, NCBR successes, pcinn.org) |
| `backend/scripts/import_*.py` | Source importers writing `backend/data/seed/<source>.json` |
| `backend/scripts/upload_innovations.py` | Uploads every seed file through the knowledge API (S3 and Qdrant) |
| `backend/scripts/import_osm_locations.py`, `seed_locations.py` | Podkarpackie administrative boundaries from OSM (`data/locations_podkarpackie.geojson`: 1 voivodeship, 25 powiats, 160 gminas) |
| `backend/scripts/seed_demo.py` | Idempotent synthetic demo data from `data/demo/demo.json` (real Interreg project texts, invented users and activity) |
| `deploy/gcp/` | Cloud Run deployment and one-time secret creation |

## Data flow

1. Importers fetch public data, classify it with keyword rules and write seed JSON.
2. `upload_innovations.py` sends each record to `PUT /api/v1/knowledge/innovations/{id}`; cards and document chunks are embedded into Qdrant.
3. The chat searches Qdrant, validates candidates (`select_innovations`) and reviews its answer against retrieved passages before replying.
4. Submissions become matters (`application_draft`) with a generated "similar solutions" section; users can download a summary PDF for PCI.
5. Pilot partners join the pool and apply to innovations; admins approve, reject or assign them.

## Run and validate

See [docs/DEVELOPMENT.md](DEVELOPMENT.md).
Backend: `uv run python -m compileall -q app scripts` and `uv run python -c "import app.main"`.
Frontend: `pnpm exec next typegen`, `pnpm exec tsc --noEmit`, `pnpm lint`, `pnpm build`.

## Product boundaries

PCI operates the product for many public institutions. Creators report innovations; institutions, companies, investors and experts look for solutions to deploy, pilot or fund. Administrators manage the knowledge base and partner pool. Innovation classification covers sector, innovation type, source institution type and maturity. Preserve institution, public authors, source URL and import date when editing imported cards.

## Not implemented

- Patent sources (UPRP blocked; EPO OPS needs a key).
- Renaming the internal `tester` identifiers to `pilot`.

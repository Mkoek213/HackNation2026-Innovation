# Local development

The project runs as two processes: the Next.js frontend and the FastAPI backend `app.main:app`.
Locally the backend can use SQLite; Docker Compose runs it against PostgreSQL, Qdrant, SeaweedFS (S3) and the production frontend.

## Setup

Use Node >=22.13.0 and pnpm 11.7.0 as declared in [package.json](../frontend/package.json), and uv with Python 3.13.

From the repository root:

```bash
cp .env.example .env
# Fill in GEMINI_API_KEY, FASTINO_API_KEY and RADAR_ADMIN_TOKEN.
docker compose up --build -d
```

The root `.env` is the only configuration source: Compose passes it to the backend through `env_file`, to PostgreSQL for its database variables, and to the frontend as build arguments.
`.env` is ignored by Git; `.env.example` is versioned.
Rebuild the frontend after changing its URLs.
Compose uses its own Qdrant at `http://qdrant:6333`, with persistent `qdrant-data` storage and no host port. To use Qdrant Cloud, set `QDRANT_URL` and `QDRANT_API_KEY` instead. Keep a separate Radar collection.
If the default host ports (3000, 8000, 5432, 8333) are taken, change `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_PORT` and `S3_PORT` together with the URLs that use them.

For direct runs without Compose, use runtime `--env-file` options and override the Compose-only hostnames:

```bash
cd backend
uv sync --locked
DATABASE_URL=sqlite+aiosqlite:///./dev.db uv run --env-file ../.env uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
pnpm install --frozen-lockfile
BACKEND_URL=http://127.0.0.1:8000 node --env-file=../.env node_modules/next/dist/bin/next dev
```

Open `http://localhost:3000`.
The home page and the innovation base are public; the chat at `/rozmowa` asks for a demo role (Użytkownik or Administrator) and then loads the persisted workspace.
Interactive API docs are at `http://127.0.0.1:8000/docs.html`; the schema is `/openapi.json`.
Set `ADMIN_USERNAME`/`ADMIN_PASSWORD` to create a bootstrap admin.

`NEXT_PUBLIC_API_BASE_URL` is embedded into browser code at build time; never put secrets in it.
Browser origins allowed by backend CORS and by the Next.js `/api/backend` proxy are configured with `ALLOWED_HOSTS` (and `FRONTEND_BASE_URL` as a fallback).
Mutating proxy requests must send an `Origin` listed there.

## Database migrations

PostgreSQL schemas are managed by Alembic (`backend/alembic.ini`, `backend/migrations/`); the schema starts from the single revision `0001`.
From `backend/`, with `DATABASE_URL` pointing at PostgreSQL:

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"   # after changing models
```

Autogenerate emits a duplicate `CheckConstraint` next to every `Enum(create_constraint=True)` column; delete the explicit duplicate before applying.
The Docker entrypoint runs `alembic upgrade head` and seeds the Podkarpackie locations before starting Uvicorn.
On SQLite the application creates missing tables at startup.

PostgreSQL initialises credentials only when its data volume is first created; changing `POSTGRES_PASSWORD` later does not change the existing role.

## Data

```bash
cd backend
uv run python scripts/import_interreg.py > data/seed/interreg.json   # Interreg 2021-2027, lead partner in Podkarpackie
uv run python scripts/import_radon.py > data/seed/radon.json         # RAD-on projects of Podkarpacie universities
cd ..
set -a && . ./.env && set +a
uv --project backend run python backend/scripts/upload_innovations.py --api "http://localhost:${BACKEND_PORT}" --dry-run
uv --project backend run python backend/scripts/upload_innovations.py --api "http://localhost:${BACKEND_PORT}"
docker compose exec backend python scripts/seed_demo.py               # demo users, topics, partners and activity
```

`upload_innovations.py` reads every `backend/data/seed/*.json` and uses the same endpoint as the admin "Dokumenty" view, so cards land in Qdrant (`QDRANT_COLLECTION`) and files in S3.
Sources, filters and limitations are recorded in [the data source investigation](DATA-SOURCES.md).

## Validation

No automated tests (see [AGENTS.md](../AGENTS.md)).

From `backend/`:

```bash
uv run python -m compileall -q app scripts
uv run python -c "import app.main"
```

From `frontend/`:

```bash
pnpm exec next typegen
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

Then run the stack and check the flows in a browser at desktop and 390px widths: home, chat with the submission creator, Moje sprawy, the innovation base and its dialog, pilot sign-up and application, admin views, contact.
Check keyboard focus, the skip link and headings; these checks do not establish WCAG certification.

## Local document storage

SeaweedFS stores knowledge sources (`innovations/...`) and project PDFs (`projects/...`) in one private bucket created by `s3-init`.
The backend streams files after its own access check.
Its endpoint is `http://localhost:${S3_PORT}` on the host and `http://s3:8333` in Compose.
`docker compose down` preserves files; `docker compose down -v` removes the volumes.

## Chat provider

The chat uses the Gemini Developer API through `google-genai` (`client.aio.models.generate_content_stream`), model `CHAT_GEMINI_MODEL` (default `gemini-3.1-flash-lite`).
Automatic function execution and SDK retries are disabled; the orchestrator in `backend/app/chat/service.py` runs tools itself and enforces the turn deadline and the input, output and tool-call budgets from `.env`.
Only `GEMINI_API_KEY` is accepted, and it stays backend-only.
Google documents 55-day abuse-monitoring retention for prompts and outputs; account tier and region determine training use, so do not send sensitive personal data.

A billable smoke check (at most three short generations, no retrieval or database):

```bash
cd backend
uv run --env-file ../.env python -m app.chat.smoke
```

Dense knowledge vectors come from `gemini-embedding-2` (`EMBEDDING_DIMENSIONS=1536`) with the same key; BM25 sparse vectors are computed in process.
A collection is bound to one embedding model and size: after changing them, set a new `QDRANT_COLLECTION` and run `scripts/reindex_knowledge.py <old collection>` in the backend container.

## Session settings

Keep the `.env.example` defaults for local HTTP: `AUTH_TOKEN_LOCATION=cookie`, `USE_CSRF_PROTECTION=true`, `AUTH_COOKIE_SAMESITE=lax`, `AUTH_COOKIE_SECURE=false`.
Use `AUTH_COOKIE_SECURE=true` and `CHAT_OWNER_COOKIE_SECURE=true` behind HTTPS.
If changing `CSRF_HEADER_NAME`, pass the same value to both runtimes.

## Summary e-mail (optional SMTP)

The contact dialog in the chat offers "Wyślij e-mail z PDF" when SMTP is configured; otherwise it falls back to PDF download and `mailto:`.
Set `SMTP_HOST`, `SMTP_FROM` and the port; set `SMTP_USERNAME`/`SMTP_PASSWORD` when required.
For port 587 use `SMTP_STARTTLS=true`, `SMTP_USE_SSL=false`; for port 465 use the opposite.
Contact form messages are always stored and, with SMTP, also sent to `RADAR_CONTACT_EMAIL`.

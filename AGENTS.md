# Radar innowacji

HackNation 2026 project for Podkarpackie Centrum Innowacji (PCI): discover public-institution innovations, describe them with evidence, find similar solutions and connect creators with pilot partners. The brief is in [docs/CHALLENGE.md](docs/CHALLENGE.md).

## Working here

- Work directly from the user's request. For substantial changes, give a short plan in chat, then implement and verify it. Create specifications only when explicitly requested.
- This is a hackathon: choose the smallest complete change and reuse existing code. Preserve unrelated work.
- Do not write or run automated tests. Validate with static checks, builds, live API calls and the running UI; report what actually passed and what remains unchecked.
- Write product copy and materials for judges in Polish. Write code, comments, development docs and Git messages in English. Match the user's conversation language.
- Keep credentials in the ignored root `.env`; never print them or put secrets in `NEXT_PUBLIC_*`. Keep shared agent instructions and skills in Git.
- Use existing authorization for Git and external actions. A request to deploy uses `deploy/gcp/deploy.ps1`; read [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) first. GCP project and URLs are still placeholders.

## Code and checks

- `frontend/`: Next.js App Router, React, TypeScript, Tailwind. Routes compose `features/<id>/index.ts`; cross-feature imports use public entry points. Before UI changes, read [frontend/DESIGN-STYLE.md](frontend/DESIGN-STYLE.md); consult [docs/MODULES.md](docs/MODULES.md) for feature boundaries.
- `backend/`: one FastAPI app at `app.main:app`, async SQLAlchemy, PostgreSQL, Gemini chat, Qdrant retrieval and S3 documents. For API or persistence changes, read [backend/API.md](backend/API.md) and [backend/DATABASE.md](backend/DATABASE.md); generated `/openapi.json` and Pydantic schemas are the contract.
- Backend checks, from `backend/`: `uv run python -m compileall -q app scripts` and `uv run python -c "import app.main"`.
- Frontend checks, from `frontend/`: `pnpm exec next typegen`, `pnpm exec tsc --noEmit`, `pnpm lint`, `pnpm build`.
- Run the stack with `docker compose up --build -d`. Root `.env` controls ports; avoid stopping other projects or deleting volumes. Full setup and manual checks: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Context when needed

- Architecture, data flow and unimplemented features: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Data imports, regional filters and source limitations: [docs/DATA-SOURCES.md](docs/DATA-SOURCES.md). Keep provenance; store creators only from public sources or with consent.
- Chat and PDF retrieval: [docs/RAG-WORKFLOW.md](docs/RAG-WORKFLOW.md). Fastino integration: [docs/FASTINO.md](docs/FASTINO.md). Vendor claims are not project validation.
- Three local skills cover repeatable operations: `run-app`, `import-data`, `deploy-radar`. They live in `.agents/skills/`; `.claude/skills` points to the same files.

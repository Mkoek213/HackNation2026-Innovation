# Radar innowacji

HackNation 2026 project for the Podkarpackie Centrum Innowacji (PCI) challenge: find innovations in public institutions, describe them with evidence, search for similar solutions and connect creators with partners who can deploy, pilot or fund them.

The app includes a Polish chat with the opt-in "Kreator zgłoszenia", Moje sprawy, an innovation knowledge base, contact and administrator views. It runs a Next.js frontend and one FastAPI backend with PostgreSQL, Gemini, Qdrant and S3-compatible storage. Interreg and RAD-on importers supply public records from Podkarpacie.

Potential scoring against explicit criteria and justified development-path recommendations remain unimplemented.

## Run locally

```bash
cp .env.example .env
# Fill in GEMINI_API_KEY, FASTINO_API_KEY and RADAR_ADMIN_TOKEN.
docker compose up --build -d
```

Open the frontend port from `.env` (`FRONTEND_PORT`, default 3000). Change the host ports if another project uses them. `.env` is ignored by Git; `NEXT_PUBLIC_*` values are public and must never contain secrets.

Setup, data loading and manual validation: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
Deployment: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md); the Radar GCP project is not provisioned yet.

## Work with an agent

Describe the result you need and any constraints. The agent inspects the relevant code, makes the change, runs appropriate checks and reports the evidence. Larger tasks can start with a short plan in chat. Specifications, task lifecycle files and execution reports are not required.

[AGENTS.md](AGENTS.md) holds the shared project instructions; [CLAUDE.md](CLAUDE.md) imports them for Claude Code. Three project skills cover repeatable operations: `/run-app`, `/import-data` and `/deploy-radar`. Claude Code discovers them through `.claude/skills`, linked to `.agents/skills` for other agents. No extra hooks or agent orchestration are required.

This setup follows Anthropic's guidance to keep [project instructions short](https://code.claude.com/docs/en/best-practices) and put [repeated procedures in skills](https://code.claude.com/docs/en/skills).

## Project references

- [Challenge and demo criteria](docs/CHALLENGE.md)
- [Architecture and current limitations](docs/ARCHITECTURE.md)
- [Data sources and import limitations](docs/DATA-SOURCES.md)
- [API](backend/API.md) and [database](backend/DATABASE.md)
- [Frontend feature boundaries](docs/MODULES.md) and [design style](frontend/DESIGN-STYLE.md)

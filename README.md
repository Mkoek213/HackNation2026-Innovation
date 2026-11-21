# Radar innowacji

HackNation 2026 project for the Podkarpackie Centrum Innowacji (PCI) challenge: discover existing Polish innovations in technology, education and administration, assess them against the five criteria of the challenge FAQ, compare them and recommend recipients and a deployment path.

The app includes a searchable catalog of about 1400 cards from all of Poland with filters, comparison and per-criterion assessment, a Polish search-advisor chat with the opt-in "Zgłoś kandydata" report, Moje sprawy, contact and administrator views. It runs a Next.js frontend and one FastAPI backend with PostgreSQL, Gemini, Qdrant and S3-compatible storage. Importers for public deployment reports, the European Funds 2014-2020 project list, CORDIS, Interreg and RAD-on supply the records.

Credibility is scored by fixed rules; the other criteria, recipients, path and measures are Gemini estimates labelled as such and need a valid `GEMINI_API_KEY`.

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

---
name: import-data
description: Refresh or upload Radar innovation records from public sources, or seed the local demo.
---

Read [docs/DATA-SOURCES.md](../../../docs/DATA-SOURCES.md) for regional filters and source limitations, and [docs/DEVELOPMENT.md](../../../docs/DEVELOPMENT.md#data) for commands.

- Reuse `backend/scripts/import_interreg.py` and `import_radon.py`; each writes one `backend/data/seed/<source>.json`. Existing seed files can be uploaded without fetching sources again. Validate refreshed JSON before replacing a seed file.
- Keep institution, source URL, import date and publicly named creators. Keyword labels are provisional; RAD-on research records do not establish innovation maturity.
- Confirm the backend URL and Qdrant collection from `.env`. Use the Radar collection, preserving other projects' data. Load credentials without printing them.
- Run `upload_innovations.py --dry-run`, then upload through the knowledge API with `--api` pointing at the configured backend port. Inspect failed records and confirm the catalog count and a retrieved result.
- For demo activity run `docker compose exec backend python scripts/seed_demo.py`. It is idempotent; its users and activity are synthetic. Report actual record counts and any failures.

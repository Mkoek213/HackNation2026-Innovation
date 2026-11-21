---
name: run-app
description: Start the local Radar stack and verify product behavior after changes, using live API and browser checks.
---

Read [docs/DEVELOPMENT.md](../../../docs/DEVELOPMENT.md) for setup, commands and verification flows.

1. Check the worktree, existing containers and port usage. Preserve existing `.env` values; if missing, copy `.env.example` and configure available provider credentials without printing them. Set free host ports and matching frontend origins.
2. Run `docker compose config --quiet`, then `docker compose up --build -d`. Check `docker compose ps`, backend startup logs and `/healthcheck` on `BACKEND_PORT`.
3. Run static checks for changed code using AGENTS.md. Use the running frontend on `FRONTEND_PORT` to check the affected flow at desktop and 390px widths, including keyboard access, errors and persistence after reload. For chat or retrieval changes, verify a real provider answer with source evidence.
4. Report the actual URL, checks and limitations. Missing provider credentials or data mean those flows remain unverified; a successful build alone does not verify them.

Keep generated screenshots and diagnostic files in `/tmp`. Leave other projects and Docker volumes intact.

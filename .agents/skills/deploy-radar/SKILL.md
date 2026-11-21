---
name: deploy-radar
description: Deploy Radar to Google Cloud Run with the repository deployment script when deployment is requested.
---

Read [docs/DEPLOYMENT.md](../../../docs/DEPLOYMENT.md) and inspect `deploy/gcp/deploy.ps1` before deploying.

1. Check that the GCP project, service URLs and environment files contain the intended target; `CHANGE-ME` placeholders are not a configured environment. Resolve missing target information before creating cloud resources.
2. Check the worktree and relevant build/static checks. Confirm Docker, PowerShell and the signed-in gcloud project; keep secrets out of logs, Git and frontend public variables.
3. Within the user's deployment authorization, run `pwsh -NoProfile -File deploy/gcp/deploy.ps1`, using `-Only backend` or `-Only frontend` when appropriate. Use the same script with Windows PowerShell on Windows.
4. Check the script's health probes and backend startup/migration logs. Verify the affected public flow and report the actual deployed URL and any remaining issue.

Use existing cloud configuration and secrets; provisioning a new environment needs its own concrete target and scope.

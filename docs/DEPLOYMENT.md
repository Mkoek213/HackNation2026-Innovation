# Deployment (Google Cloud Run)

The deployment scripts target Google Cloud in region `europe-central2` (Warsaw).
GCP project `radar-innowacji` (number 138165247544).
Deployed first on 2026-11-22; data (Qdrant collection, Postgres, documents) was copied 1:1 from the local stack.

| What | Value |
| --- | --- |
| Frontend (app) | https://radar-frontend-138165247544.europe-central2.run.app |
| Backend (API) | https://radar-backend-138165247544.europe-central2.run.app (`/healthcheck`) |
| Images | `europe-central2-docker.pkg.dev/radar-innowacji/radar/{backend,frontend}` |
| Database | Cloud SQL Postgres 17 `radar-db` (`db-f1-micro`, no automated backups), database and user `radar` |
| File storage | GCS bucket `radar-innowacji-radar-documents`, accessed through the S3 API with an HMAC key |
| Backend identity | Service account `radar-backend@radar-innowacji.iam.gserviceaccount.com` (Cloud SQL client, Secret Manager accessor, bucket object admin) |

## Deploying a new version

Prerequisites on the workstation: Docker running, `gcloud` logged in with the project set.

```powershell
powershell -ExecutionPolicy Bypass -File deploy/gcp/deploy.ps1                  # backend + frontend
powershell -ExecutionPolicy Bypass -File deploy/gcp/deploy.ps1 -Only backend
powershell -ExecutionPolicy Bypass -File deploy/gcp/deploy.ps1 -Only frontend
```

On Linux/macOS, use PowerShell 7 (`pwsh`) with the same script:

```bash
gcloud config set project radar-innowacji
gcloud config set run/region europe-central2
pwsh -NoProfile -File deploy/gcp/deploy.ps1                  # backend + frontend
pwsh -NoProfile -File deploy/gcp/deploy.ps1 -Only backend
pwsh -NoProfile -File deploy/gcp/deploy.ps1 -Only frontend
```

Use `gcloud auth login` if no account is signed in. The signed-in account needs
Cloud Run deployment permissions, image upload access to the `radar` Artifact Registry
repository, and permission to act as the backend service account. The deployment
script configures Docker authentication automatically; local Application Default
Credentials are not needed for this script.

The script builds both images locally, tags them with the Git short SHA (plus `-dirty-<timestamp>` for uncommitted changes) and `latest`,
pushes them, runs `gcloud run deploy` with the full service configuration, and smoke-tests `/healthcheck` and the frontend root.
Database migrations run automatically: the backend entrypoint executes `alembic upgrade head` on start.

After deploying, check the backend startup logs for migration or runtime errors:

```powershell
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="radar-backend"' --limit 50 --freshness=15m --format="value(severity,textPayload)"
```

Roll back by routing traffic to an earlier revision:

```powershell
gcloud run revisions list --service radar-backend --region europe-central2
gcloud run services update-traffic radar-backend --region europe-central2 --to-revisions <REVISION>=100
```

## Configuration

- Non-secret environment: [deploy/gcp/backend-env.yaml](../deploy/gcp/backend-env.yaml) and
  [deploy/gcp/frontend-env.yaml](../deploy/gcp/frontend-env.yaml). Add new variables there and redeploy.
- Secrets live in Secret Manager and are mounted as environment variables by `deploy.ps1`:
  `radar-database-url` (`DATABASE_URL`, Cloud SQL unix socket), `radar-jwt-secret`, `radar-csrf-secret`, `radar-admin-password`,
  `radar-s3-access-key-id`, `radar-s3-secret-access-key`, `radar-gemini-api-key` (`GEMINI_API_KEY`), `radar-qdrant-url`, `radar-qdrant-api-key`,
  `radar-fastino-api-key`, `radar-admin-token` (`RADAR_ADMIN_TOKEN`, knowledge writes and the scheduled tagging sweep), and `radar-db-password` (reference only).
  For a new project, inspect and configure [deploy/gcp/create-secrets.ps1](../deploy/gcp/create-secrets.ps1) before creating them. Preserve existing secrets.
  To add a secret: `gcloud secrets create <name> --data-file=<file>`, then add it to `--set-secrets` in `deploy.ps1`.
- The frontend bakes `BACKEND_URL` and `NEXT_PUBLIC_API_BASE_URL` in at build time. Renaming the backend service requires a frontend rebuild.
- Cloud Run URLs are deterministic (`https://<service>-138165247544.europe-central2.run.app`), so both URLs are hardcoded in the script and env files after the first deploy.

### Scheduled conversation tagging

Cloud Run allocates CPU only while a request is being served, so the backend runs no background loop there (`TAGGING_SWEEP_SECONDS=0`).
Cloud Scheduler job `tag-conversations` (region `europe-central2`, every 5 minutes) calls `POST /internal/tagging/sweep` with the `X-Admin-Token` header from `radar-admin-token`.
`deploy.ps1` creates or updates the job on every backend deploy.
Each run logs `Conversation tagging: due=... tagged=... failed=...`; see [Fastino](FASTINO.md#topic-tagging) for the rules.

### Deliberate settings and caveats

- PoC chat budgets: 128 tool executions per turn, 250000 UTF-8 context bytes and
  8192 output tokens per generation; total turn deadline 600 seconds. Workspace
  timeout is 630 seconds, chat BFF timeout 660 seconds, browser timeout 690 seconds,
  and processing lease 720 seconds. Both Cloud Run services use a 900-second request
  timeout. These ceilings allow longer turns; ordinary requests keep their existing deadlines.
- `S3_ENDPOINT_URL=https://storage.googleapis.com` with `AWS_REQUEST_CHECKSUM_CALCULATION` and `AWS_RESPONSE_CHECKSUM_VALIDATION` set to `when_required`:
  recent boto3 sends checksum headers GCS rejects otherwise. File upload through the app has not yet been verified end to end.
- `PROXY_TRUSTED_HOSTS=["*"]` so the rate limiter sees the client IP behind the Cloud Run front end. `X-Forwarded-For` can be spoofed to dodge rate limits; acceptable for the demo only.
- `REQUIRE_TRUSTED_HOSTS=false`, `AUTH_COOKIE_SECURE=true`, `DEBUG=false`.
- Gemini, Qdrant (collection `radar_innovations`) and Fastino come from Secret Manager.
  The workspace chat on the frontend answers with the Gemini agent; `AI_BACKEND=demo` only affects the older `/conversations` API.
- Dense embeddings come from the Gemini API (`gemini-embedding-2`, 1536 dimensions, same `GEMINI_API_KEY` as the chat) and BM25 is computed in process,
  so the backend image bundles no embedding model. The backend runs with 1 CPU and 2 GiB (about 240 MiB at idle; the headroom is for PDF and archive extraction during uploads).
  Collection `radar_innovations` is reserved for these vectors; preserve collections belonging to other projects.
- API keys live only in the local `.env` (gitignored, excluded by `.dockerignore`) and in Secret Manager; never put them in the YAML files, images or Git.
  To rotate one: `gcloud secrets versions add <name> --data-file=-` (pipe the value in), then redeploy the backend.
- Both services keep `--min-instances 1` to avoid cold starts during judging; costs roughly Cloud SQL ~10 USD/month plus the idle instances.

## Accounts

- Admin: username `admin`, password in Secret Manager:
  `gcloud secrets versions access latest --secret radar-admin-password`.
  The admin is created on first start only if it does not exist; changing the secret later does not change the existing account's password.
- The local demo frontend creates its fixed demo user or administrator account on entry; those are not evidence of accounts provisioned in Cloud Run.

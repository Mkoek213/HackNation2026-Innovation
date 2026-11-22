# Builds the backend and frontend images locally, pushes them to Artifact Registry,
# and deploys them to Cloud Run. See docs/DEPLOYMENT.md.
#
#   powershell -ExecutionPolicy Bypass -File deploy/gcp/deploy.ps1                  # both services
#   powershell -ExecutionPolicy Bypass -File deploy/gcp/deploy.ps1 -Only backend
#   powershell -ExecutionPolicy Bypass -File deploy/gcp/deploy.ps1 -Only frontend
param(
    [ValidateSet('all', 'backend', 'frontend')]
    [string]$Only = 'all'
)
$ErrorActionPreference = 'Stop'

$Project = 'radar-innowacji'
$Region = 'europe-central2'
$Registry = "$Region-docker.pkg.dev/$Project/radar"
$BackendUrl = 'https://radar-backend-138165247544.europe-central2.run.app'
$FrontendUrl = 'https://radar-frontend-138165247544.europe-central2.run.app'
$Here = $PSScriptRoot
$Root = (Resolve-Path (Join-Path $Here '../..')).Path

function Invoke-Checked([string]$What, [scriptblock]$Command) {
    Write-Host "==> $What"
    # Native tools log progress to stderr; rely on the exit code instead of PowerShell error records.
    $ErrorActionPreference = 'Continue'
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit $LASTEXITCODE)" }
}

$Tag = (git -C $Root rev-parse --short HEAD).Trim()
if (git -C $Root status --porcelain) { $Tag = "$Tag-dirty-$(Get-Date -Format 'yyyyMMddHHmmss')" }
Write-Host "Image tag: $Tag"

Invoke-Checked 'Configure Docker auth' { gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet }

if ($Only -in 'all', 'backend') {
    Invoke-Checked 'Build backend' {
        docker build -f (Join-Path $Root 'backend/docker/Dockerfile') --build-arg "CI_COMMIT_SHORT_SHA=$Tag" `
            -t "$Registry/backend:$Tag" -t "$Registry/backend:latest" (Join-Path $Root 'backend')
    }
    Invoke-Checked 'Push backend' { docker push --all-tags "$Registry/backend" }
    # Secrets come from Secret Manager (created once by create-secrets.ps1); values never pass through here.
    Invoke-Checked 'Deploy backend' {
        gcloud run deploy radar-backend --project $Project --region $Region `
            --image "$Registry/backend:$Tag" `
            --service-account "radar-backend@$Project.iam.gserviceaccount.com" `
            --add-cloudsql-instances "${Project}:${Region}:radar-db" `
            --port 8000 --memory 2Gi --cpu 1 --min-instances 1 --max-instances 3 --timeout 900s `
            --allow-unauthenticated `
            --env-vars-file (Join-Path $Here 'backend-env.yaml') `
            --set-secrets 'DATABASE_URL=radar-database-url:latest,JWT_SECRET=radar-jwt-secret:latest,CSRF_SECRET=radar-csrf-secret:latest,ADMIN_PASSWORD=radar-admin-password:latest,S3_ACCESS_KEY_ID=radar-s3-access-key-id:latest,S3_SECRET_ACCESS_KEY=radar-s3-secret-access-key:latest,GEMINI_API_KEY=radar-gemini-api-key:latest,QDRANT_URL=radar-qdrant-url:latest,QDRANT_API_KEY=radar-qdrant-api-key:latest,FASTINO_API_KEY=radar-fastino-api-key:latest,RADAR_ADMIN_TOKEN=radar-admin-token:latest' `
            --quiet
    }
    # Cloud Run allocates CPU only during requests, so Cloud Scheduler drives the idle-conversation tagging sweep.
    Invoke-Checked 'Schedule conversation tagging' {
        $Token = (gcloud secrets versions access latest --secret radar-admin-token --project $Project).Trim()
        # --format none: the job description includes the token header.
        $Job = @('tag-conversations', '--project', $Project, '--location', $Region, '--schedule', '*/5 * * * *',
            '--uri', "$BackendUrl/internal/tagging/sweep", '--http-method', 'POST', '--attempt-deadline', '180s', '--quiet', '--format', 'none')
        gcloud scheduler jobs describe tag-conversations --project $Project --location $Region --format 'value(name)' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            gcloud scheduler jobs update http @Job --update-headers "X-Admin-Token=$Token"
        } else {
            gcloud scheduler jobs create http @Job --headers "X-Admin-Token=$Token"
        }
    }
}

if ($Only -in 'all', 'frontend') {
    # BACKEND_URL and NEXT_PUBLIC_API_BASE_URL are baked in at build time (Next.js rewrites/public env).
    Invoke-Checked 'Build frontend' {
        docker build -f (Join-Path $Root 'frontend/Dockerfile') `
            --build-arg "BACKEND_URL=$BackendUrl" --build-arg "NEXT_PUBLIC_API_BASE_URL=$BackendUrl" `
            -t "$Registry/frontend:$Tag" -t "$Registry/frontend:latest" (Join-Path $Root 'frontend')
    }
    Invoke-Checked 'Push frontend' { docker push --all-tags "$Registry/frontend" }
    Invoke-Checked 'Deploy frontend' {
        gcloud run deploy radar-frontend --project $Project --region $Region `
            --image "$Registry/frontend:$Tag" `
            --port 3000 --memory 512Mi --cpu 1 --min-instances 1 --max-instances 3 --timeout 900s `
            --allow-unauthenticated `
            --env-vars-file (Join-Path $Here 'frontend-env.yaml') `
            --quiet
    }
}

Write-Host '==> Smoke test'
$health = Invoke-WebRequest -UseBasicParsing "$BackendUrl/healthcheck"
$front = Invoke-WebRequest -UseBasicParsing "$FrontendUrl/"
Write-Host "backend /healthcheck: $($health.StatusCode)  frontend /: $($front.StatusCode)"
Write-Host "Deployed $Tag -> $FrontendUrl"

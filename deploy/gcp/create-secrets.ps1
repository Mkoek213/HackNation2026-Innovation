# Creates the GCS HMAC key, random app secrets in Secret Manager, and the Cloud SQL database/user.
# No secret value is printed; temp files are removed at the end.
$ErrorActionPreference = 'Stop'
$P = 'CHANGE-ME-gcp-project'
$SA = "radar-backend@$P.iam.gserviceaccount.com"
$T = Join-Path $env:TEMP ("radar-secrets-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $T | Out-Null

function New-RandomSecret {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-RadarSecret([string]$Name, [string]$Value) {
    $file = Join-Path $T $Name
    # No BOM, no trailing newline.
    [IO.File]::WriteAllText($file, $Value, (New-Object Text.UTF8Encoding $false))
    gcloud secrets create $Name --data-file=$file --replication-policy=automatic --project $P | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create secret $Name" }
    Write-Host "created secret $Name"
}

try {
    $hmacJson = gcloud storage hmac create $SA --project $P --format=json
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create HMAC key' }
    $hmac = ($hmacJson -join "`n") | ConvertFrom-Json

    $dbPass = New-RandomSecret
    New-RadarSecret 'radar-jwt-secret' (New-RandomSecret)
    New-RadarSecret 'radar-csrf-secret' (New-RandomSecret)
    New-RadarSecret 'radar-db-password' $dbPass
    New-RadarSecret 'radar-admin-password' (New-RandomSecret)
    New-RadarSecret 'radar-s3-access-key-id' $hmac.metadata.accessId
    New-RadarSecret 'radar-s3-secret-access-key' $hmac.secret
    New-RadarSecret 'radar-database-url' "postgresql+asyncpg://radar:$dbPass@/radar?host=/cloudsql/${P}:europe-central2:radar-db"

    Write-Host 'waiting for Cloud SQL instance radar-db...'
    while ((gcloud sql instances describe radar-db --project $P --format='value(state)') -ne 'RUNNABLE') {
        Start-Sleep -Seconds 15
    }
    gcloud sql databases create radar --instance=radar-db --project $P
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create database' }
    gcloud sql users create radar --instance=radar-db --project $P --password=$dbPass
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create database user' }
    Write-Host 'done'
}
finally {
    Remove-Item -Recurse -Force $T
}

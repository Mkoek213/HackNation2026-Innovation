# Creates the GCS HMAC key, random app secrets in Secret Manager, and the Cloud SQL database/user.
# No secret value is printed; temp files are removed at the end.
$ErrorActionPreference = 'Stop'
$P = 'radar-innowacji'
$SA = "radar-backend@$P.iam.gserviceaccount.com"
$T = Join-Path ([IO.Path]::GetTempPath()) ("radar-secrets-" + [guid]::NewGuid())
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

# radar-qdrant-* were copied from the shared HackYeah cluster secrets. API keys come from the root .env (never printed); RADAR_ADMIN_TOKEN is generated when empty.
$DotEnv = @{}
Get-Content (Join-Path $PSScriptRoot '../../.env') | Where-Object { $_ -match '^\s*([A-Z0-9_]+)=(.*)$' } |
    ForEach-Object { $DotEnv[$Matches[1]] = $Matches[2].Trim().Trim('"') }

try {
    foreach ($pair in @(@('radar-gemini-api-key', 'GEMINI_API_KEY'),
            @('radar-fastino-api-key', 'FASTINO_API_KEY'))) {
        if (-not $DotEnv[$pair[1]]) { throw "$($pair[1]) missing in .env" }
        New-RadarSecret $pair[0] $DotEnv[$pair[1]]
    }
    $adminToken = if ($DotEnv['RADAR_ADMIN_TOKEN']) { $DotEnv['RADAR_ADMIN_TOKEN'] } else { New-RandomSecret }
    New-RadarSecret 'radar-admin-token' $adminToken
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

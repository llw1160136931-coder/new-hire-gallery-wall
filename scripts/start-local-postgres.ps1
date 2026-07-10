$ErrorActionPreference = 'Stop'

$portableRoot = 'C:\Users\Public\NewHireGallery\PostgreSQL17\pgsql'
$pgRoot = if (Test-Path (Join-Path $portableRoot 'bin\pg_ctl.exe')) {
    Get-Item $portableRoot
} else {
    Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'bin\pg_ctl.exe') } |
        Sort-Object { [int]$_.Name } -Descending |
        Select-Object -First 1
}

if (-not $pgRoot) {
    throw 'PostgreSQL is not installed under C:\Program Files\PostgreSQL.'
}

$dataDir = 'C:\Users\Public\NewHireGallery\PostgreSQL17\data'
$logDir = 'C:\Users\Public\NewHireGallery\PostgreSQL17'
$pgCtl = Join-Path $pgRoot.FullName 'bin\pg_ctl.exe'

if (-not (Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    throw "Local database cluster is not initialized: $dataDir"
}

& $pgCtl status -D $dataDir *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Output 'Local PostgreSQL is already running on 127.0.0.1:55432.'
    exit 0
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
& $pgCtl start -D $dataDir -l (Join-Path $logDir 'postgresql.log') -o '"-p 55432 -h 127.0.0.1 -c max_connections=200"' -w
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to start local PostgreSQL.'
}
Write-Output 'Local PostgreSQL started on 127.0.0.1:55432.'

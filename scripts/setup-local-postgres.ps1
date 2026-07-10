$ErrorActionPreference = 'Stop'

$portableRoot = 'C:\Users\Public\NewHireGallery\PostgreSQL17\pgsql'
$pgRoot = if (Test-Path (Join-Path $portableRoot 'bin\initdb.exe')) {
    Get-Item $portableRoot
} else {
    Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'bin\initdb.exe') -and [int]$_.Name -ge 14 } |
        Sort-Object { [int]$_.Name } -Descending |
        Select-Object -First 1
}

if (-not $pgRoot) {
    throw 'PostgreSQL 14 or newer is required.'
}

$pgBin = Join-Path $pgRoot.FullName 'bin'
$dataDir = 'C:\Users\Public\NewHireGallery\PostgreSQL17\data'
if (-not (Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $dataDir) | Out-Null
    & (Join-Path $pgBin 'initdb.exe') -D $dataDir -U postgres --encoding=UTF8 --locale=C --auth-host=trust --auth-local=trust
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to initialize local PostgreSQL.'
    }
}

& (Join-Path $PSScriptRoot 'start-local-postgres.ps1')

$roleExists = & (Join-Path $pgBin 'psql.exe') -h 127.0.0.1 -p 55432 -U postgres -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='gallery_app'"
if ($roleExists -ne '1') {
    & (Join-Path $pgBin 'psql.exe') -h 127.0.0.1 -p 55432 -U postgres -d postgres -v ON_ERROR_STOP=1 -c 'CREATE ROLE gallery_app LOGIN CREATEDB;'
}

$databaseExists = & (Join-Path $pgBin 'psql.exe') -h 127.0.0.1 -p 55432 -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='new_hire_gallery'"
if ($databaseExists -ne '1') {
    & (Join-Path $pgBin 'createdb.exe') -h 127.0.0.1 -p 55432 -U postgres -O gallery_app -E UTF8 new_hire_gallery
}

if ($LASTEXITCODE -ne 0) {
    throw 'Failed to prepare the local application database.'
}
Write-Output 'Local PostgreSQL database new_hire_gallery is ready.'

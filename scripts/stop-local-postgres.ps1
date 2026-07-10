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
$dataDir = 'C:\Users\Public\NewHireGallery\PostgreSQL17\data'

if (-not $pgRoot -or -not (Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    Write-Output 'Local PostgreSQL cluster is not initialized.'
    exit 0
}

$pgCtl = Join-Path $pgRoot.FullName 'bin\pg_ctl.exe'
& $pgCtl status -D $dataDir *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Output 'Local PostgreSQL is already stopped.'
    exit 0
}

& $pgCtl stop -D $dataDir -m fast -w
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to stop local PostgreSQL.'
}
Write-Output 'Local PostgreSQL stopped.'

#requires -Version 5
<#
.SYNOPSIS
    The development PostgreSQL, for every app on this machine.

.DESCRIPTION
    Starts the container described by docker-compose.dev-db.yml: one server
    holding one database per app, in its own compose project so that nothing an
    app does can adopt or destroy it.

    This replaced `anime_site_postgres_db`, which lived in media's compose
    project. The rename was the visible half; the move is the point.

.PARAMETER Down
    Stop and remove the container. THE VOLUME STAYS - no data is lost.

.PARAMETER Migrate
    One-off. Copies the old anime_site_postgres_anime_data volume into
    cg1618_dev_pgdata. Refuses if the target already holds a database, so
    running it twice cannot overwrite anything. The source volume is never
    touched, and is the rollback.

.PARAMETER Force
    With -Migrate only: overwrite a target that already holds data. Ask
    yourself why first.
#>
[CmdletBinding()]
param(
    [switch]$Down,
    [switch]$Migrate,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$composeFile = Join-Path $root 'docker-compose.dev-db.yml'
$oldVolume = 'anime_site_postgres_anime_data'
$newVolume = 'cg1618_dev_pgdata'
$container = 'cg1618-dev-db'

if (-not (Test-Path $composeFile)) {
    throw "Not found: $composeFile. Run this from the platform checkout."
}

$compose = @('docker', 'compose', '-f', $composeFile)

# --- Migrate -----------------------------------------------------------------

if ($Migrate) {
    $sourceExists = (docker volume ls --quiet --filter "name=^$oldVolume$")
    if (-not $sourceExists) {
        throw "No volume named $oldVolume on this machine - nothing to migrate. If this is a fresh machine, just run .\dev-db.cmd and let postgres initialise an empty one."
    }

    # --- The old container must not be running. Copying a data directory out
    # --- from under a live postgres captures a torn snapshot: it will usually
    # --- start, and it will be subtly wrong rather than obviously broken.
    $oldRunning = docker ps --quiet --filter 'name=^anime_site_postgres_db$'
    if ($oldRunning) {
        Write-Host '==> Stopping anime_site_postgres_db before copying its data' -ForegroundColor Cyan
        Write-Host '    (stop, not down - `down` in media''s project is the defect this move removes)' -ForegroundColor DarkGray
        docker stop anime_site_postgres_db | Out-Null
    }

    # --- Let COMPOSE create the volume, rather than letting `docker run -v`
    # --- conjure it below. A volume docker made has none of compose's labels,
    # --- so every later `compose up` warns "volume already exists but was not
    # --- created by Docker Compose" - true, harmless, and exactly the kind of
    # --- warning that trains you to ignore warnings.
    Write-Host '==> Creating the volume through compose, so it carries compose''s labels' -ForegroundColor Cyan
    & $compose[0] $compose[1..3] create 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'compose create failed - are POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB set in this directory''s .env?'
    }

    $targetHasData = docker run --rm -v "${newVolume}:/target" alpine:3 sh -c 'test -f /target/PG_VERSION && echo yes || echo no'
    if ($targetHasData -eq 'yes' -and -not $Force) {
        throw "$newVolume already holds a database. Migrating again would overwrite it. Pass -Force if that is genuinely what you want."
    }

    Write-Host "==> Copying $oldVolume -> $newVolume" -ForegroundColor Cyan
    # -a preserves ownership and mode, which postgres checks: a data directory
    # owned by the wrong uid, or group-readable, makes it refuse to start.
    # The `.` matters - `cp -a /from /to` would nest it one level deeper.
    docker run --rm -v "${oldVolume}:/from:ro" -v "${newVolume}:/to" alpine:3 `
        sh -c 'cp -a /from/. /to/ && ls /to/PG_VERSION'
    if ($LASTEXITCODE -ne 0) { throw 'The copy failed. The source volume is untouched.' }

    Write-Host '==> Copied. The old volume is untouched and is your rollback.' -ForegroundColor Green
    Write-Host ''
}

# --- Down --------------------------------------------------------------------

if ($Down) {
    Write-Host '==> Stopping the development database' -ForegroundColor Cyan
    # No -v, ever, from this script. The volume is four apps' development data
    # and losing it is a day of restoring dumps.
    & $compose[0] $compose[1..3] down
    if ($LASTEXITCODE -ne 0) { throw 'compose down failed.' }
    Write-Host "==> Down. Volume $newVolume kept." -ForegroundColor Green
    return
}

# --- Up ----------------------------------------------------------------------

# --- Guard: a native PostgreSQL service binds 5432 too and usually wins the
# --- race against the container. Everything below would still report success -
# --- pg_isready runs INSIDE the container - while every app silently talks to
# --- the native server's separate, usually empty database.
$nativeSvc = @(Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue |
               Where-Object { $_.Status -eq 'Running' })
if ($nativeSvc) {
    Write-Host '==> A native PostgreSQL server is running on this machine.' -ForegroundColor Yellow
    foreach ($s in $nativeSvc) { Write-Host "      service: $($s.Name)" -ForegroundColor Yellow }
    Write-Host '    It shadows the container on 5432, and every app would run against' -ForegroundColor Yellow
    Write-Host '    the wrong database without saying so. From an elevated PowerShell:' -ForegroundColor Yellow
    $names = ($nativeSvc | ForEach-Object { $_.Name }) -join ', '
    Write-Host "      Stop-Service $names -Force" -ForegroundColor Yellow
    throw 'A native PostgreSQL server would shadow the container - aborting.'
}

# --- Guard: the old container also binds 5432. Whichever starts first wins,
# --- and the loser fails to bind - so an app could end up on the OLD database
# --- with nothing saying which one it reached.
$old = docker ps --quiet --filter 'name=^anime_site_postgres_db$'
if ($old) {
    Write-Host '==> anime_site_postgres_db is still running and holds port 5432.' -ForegroundColor Yellow
    Write-Host '    That is the container this one replaces. Stop it first:' -ForegroundColor Yellow
    Write-Host '      docker stop anime_site_postgres_db' -ForegroundColor Yellow
    Write-Host '    Its volume is untouched either way.' -ForegroundColor Yellow
    throw 'The old development database is still running - aborting rather than racing it for the port.'
}

Write-Host '==> Starting the development database' -ForegroundColor Cyan
& $compose[0] $compose[1..3] up -d
if ($LASTEXITCODE -ne 0) {
    throw 'compose up failed - is Docker Desktop running, and are POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB set in this directory''s .env?'
}

Write-Host '==> Waiting for it to accept connections' -ForegroundColor Cyan
$ready = $false
foreach ($attempt in 1..60) {
    $status = docker inspect -f '{{.State.Health.Status}}' $container 2>$null
    if ($status -eq 'healthy') { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Host '==> It did not become healthy. What it said:' -ForegroundColor Yellow
    & $compose[0] $compose[1..3] logs --tail 30 db
    throw 'The development database never became healthy.'
}

# --- What is actually in there. A migration that silently copied nothing looks
# --- exactly like a working empty database until an app cannot find its data.
$databases = docker exec $container psql -U $env:POSTGRES_USER -tAc `
    "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname" 2>$null

Write-Host ''
Write-Host "==> $container is up on 127.0.0.1:5432" -ForegroundColor Green
if ($databases) {
    Write-Host '    Databases:' -ForegroundColor DarkGray
    foreach ($d in ($databases -split "`n" | Where-Object { $_ })) {
        Write-Host "      $($d.Trim())" -ForegroundColor DarkGray
    }
}
else {
    Write-Host '    Could not list databases from here (POSTGRES_USER is not set in this' -ForegroundColor DarkGray
    Write-Host '    shell, which is normal). Check with:' -ForegroundColor DarkGray
    Write-Host "      docker exec $container psql -U <user> -l" -ForegroundColor DarkGray
}
Write-Host ''
Write-Host '    Stop with:  .\dev-db.cmd -Down    (the volume is kept)' -ForegroundColor DarkGray

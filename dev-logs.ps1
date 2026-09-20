#requires -Version 5
<#
.SYNOPSIS
    The log collector, locally. Loki + Alloy + Grafana, and nothing else.

.DESCRIPTION
    Starts the three observability containers from docker-compose.dev-logs.yml
    and opens Grafana. This is NOT the box: no tunnel, no shared PostgreSQL, no
    apex page. See the header of that compose file for why those must not start
    here.

    What it can show you is every CONTAINER on this machine. In development the
    four apps run as uvicorn processes rather than containers, so their lines
    are not here - they are in the terminal you started them in, in the plain
    human format, which is the format the contract asks for in development.
    "Viewing it locally" in docs/logging.md says what to do if you want real
    application lines.

.PARAMETER Down
    Stop and remove the containers. Volumes are kept, so history survives.

.PARAMETER Clean
    Stop and remove the containers AND their volumes, discarding local history.
#>
[CmdletBinding()]
param(
    [switch]$Down,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$composeFile = Join-Path $root 'docker-compose.dev-logs.yml'
$grafanaPort = 8008
$grafanaUrl = "http://127.0.0.1:$grafanaPort/"

if (-not (Test-Path $composeFile)) {
    throw "Not found: $composeFile. Run this from the platform checkout."
}

$compose = @('docker', 'compose', '-f', $composeFile)

if ($Down -or $Clean) {
    $verb = if ($Clean) { 'Removing containers and volumes' } else { 'Stopping' }
    Write-Host "==> $verb" -ForegroundColor Cyan
    # `down`, not `stop`: this project is its own and shares nothing, so unlike
    # a tree that shares media's compose project there is nothing for `down` to
    # take out from under anybody. See "docker compose down in any media tree"
    # in docs/open-items.md for the case where that is NOT true.
    if ($Clean) {
        & $compose[0] $compose[1..3] down -v
    }
    else {
        & $compose[0] $compose[1..3] down
    }
    if ($LASTEXITCODE -ne 0) { throw 'compose down failed.' }
    Write-Host '==> Down.' -ForegroundColor Green
    return
}

# --- Is this stack already up? Running the script twice is the ordinary thing
# --- to do, and the port guard below cannot tell "my own Grafana" from "another
# --- app stole 8008" - it sees com.docker.backend holding the port either way.
# --- Ask compose which it is before guarding on the port.
$existing = @(& $compose[0] $compose[1..3] ps -q 2>$null | Where-Object { $_ })
$alreadyUp = $existing.Count -gt 0

if (-not $alreadyUp) {
    # --- Guard: 8008 is a box-wide allocation, not a preference. apps.yml
    # --- reserves it for `logs`, and docs/dev-ports.md is explicit that taking
    # --- another port because this one is busy is how one app silently steals
    # --- another's slot. Abort rather than fall back.
    $stale = Get-NetTCPConnection -LocalPort $grafanaPort -State Listen -ErrorAction SilentlyContinue
    if ($stale) {
        $owner = Get-Process -Id $stale[0].OwningProcess -ErrorAction SilentlyContinue
        Write-Host "==> Port $grafanaPort is already in use by $($owner.ProcessName) (PID $($stale[0].OwningProcess))." -ForegroundColor Yellow
        Write-Host '    This stack is not running, so something else holds it. If a previous' -ForegroundColor Yellow
        Write-Host '    run left containers behind under another project name, find them with:' -ForegroundColor Yellow
        Write-Host '      docker ps --filter publish=8008' -ForegroundColor Yellow
        throw "Grafana's port $grafanaPort is occupied - aborting rather than taking another app's slot."
    }
}

if ($alreadyUp) {
    Write-Host '==> Already running; checking it is healthy' -ForegroundColor Cyan
}
else {
    Write-Host '==> Starting Loki, Alloy and Grafana' -ForegroundColor Cyan
}
& $compose[0] $compose[1..3] up -d
if ($LASTEXITCODE -ne 0) {
    throw 'compose up failed - is Docker Desktop running?'
}

# --- Grafana runs a database migration on first start, so the port is listening
# --- before it can answer. Poll its own health endpoint rather than the port,
# --- or the browser opens on a connection reset and it reads as broken.
Write-Host '==> Waiting for Grafana' -ForegroundColor Cyan
$ready = $false
foreach ($attempt in 1..60) {
    try {
        $response = Invoke-WebRequest -Uri "${grafanaUrl}api/health" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    Write-Host '==> Grafana did not answer in two minutes. What it said:' -ForegroundColor Yellow
    & $compose[0] $compose[1..3] logs --tail 40 grafana
    throw 'Grafana never became healthy.'
}

# --- Loki is distroless and cannot healthcheck itself, so ask it from here.
# --- /ready, not /metrics: it serves metrics before it can answer a query, so a
# --- probe on /metrics goes green while every search fails.
Write-Host '==> Waiting for Loki' -ForegroundColor Cyan
$lokiReady = $false
foreach ($attempt in 1..60) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:3100/ready' -UseBasicParsing -TimeoutSec 3
        if ($response.Content -match 'ready') { $lokiReady = $true; break }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $lokiReady) {
    Write-Host '==> Loki did not become ready. What it said:' -ForegroundColor Yellow
    & $compose[0] $compose[1..3] logs --tail 40 loki
    throw 'Loki never became ready.'
}

# --- What Alloy has actually found. An empty list here is the difference
# --- between "nothing is running" and "the socket mount did not work", and it
# --- is worth saying at startup rather than leaving to be discovered in an
# --- empty Grafana.
$containers = @()
try {
    $labels = Invoke-RestMethod -Uri 'http://127.0.0.1:3100/loki/api/v1/label/container/values' -TimeoutSec 5
    if ($labels.data) { $containers = $labels.data }
}
catch {
    # Alloy may not have pushed anything yet; not worth failing the start over.
}

Write-Host ''
Write-Host "==> Grafana:  $grafanaUrl" -ForegroundColor Green
Write-Host '    No login. Anonymous access is on for the local stack, so the page' -ForegroundColor DarkGray
Write-Host '    opens straight into Grafana. Sign in as admin / admin only if you' -ForegroundColor DarkGray
Write-Host '    want to be a real user; production has neither of those.' -ForegroundColor DarkGray
Write-Host '    Loki is provisioned as the default datasource - go to Explore.' -ForegroundColor DarkGray
Write-Host ''
if ($containers.Count -gt 0) {
    Write-Host "==> Alloy is tailing $($containers.Count) container(s):" -ForegroundColor Cyan
    foreach ($c in $containers) { Write-Host "      $c" -ForegroundColor DarkGray }
}
else {
    Write-Host '==> Alloy has not reported any containers yet. Give it fifteen seconds;' -ForegroundColor Yellow
    Write-Host '    if it stays empty, the docker socket mount is the thing to check.' -ForegroundColor Yellow
}
Write-Host ''
Write-Host '    Your four apps are NOT here: in development they run as uvicorn' -ForegroundColor DarkGray
Write-Host '    processes, not containers. See "Viewing it locally" in docs/logging.md.' -ForegroundColor DarkGray
Write-Host ''
Write-Host '    Stop with:  .\dev.cmd -Down    (or .\dev-logs.ps1 -Down)' -ForegroundColor DarkGray

Start-Process $grafanaUrl

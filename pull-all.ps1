#requires -Version 5
<#
.SYNOPSIS
    Pull the platform and every app checked out inside it, in one go.

.DESCRIPTION
    Runs `git pull --ff-only` in this repository and in each app directory
    beneath it. The app list is read from apps.yml rather than written here,
    so an app added to the registry is pulled without editing this script.

    Each repository is pulled on WHATEVER BRANCH IT HAS CHECKED OUT. That is
    deliberate - switching branches under a session working in that directory
    would move its HEAD mid-edit - but it means a repository on a feature
    branch is not brought to dev. The summary prints every branch, and any that
    is not dev or main is shown in yellow, so that case is visible rather than
    discovered later.

    Nothing here can change history or lose work:

      - --ff-only refuses a pull that would need a merge. A repository whose
        branch has diverged from its upstream is reported and left alone.
      - A repository with uncommitted changes is fetched, not pulled. A pull
        into a dirty tree usually succeeds, and that is the problem: the
        changes may be another session's, and they would be carried onto new
        code without anyone choosing to.
      - A detached HEAD, or a branch with no upstream, is fetched only.

    The exit code is 0 only when every repository was pulled or was already
    up to date, so the one-click wrapper can tell a clean run from one that
    needs a look.

.PARAMETER FetchOnly
    Fetch every repository and pull none. Updates the remote-tracking branches
    so you can see what has landed, and touches no checkout.
#>
[CmdletBinding()]
param(
    [switch]$FetchOnly
)

$root = $PSScriptRoot
$registry = Join-Path $root 'apps.yml'

if (-not (Test-Path $registry)) {
    Write-Host "Not found: $registry. Run this from the platform checkout." -ForegroundColor Red
    exit 2
}

# --- Line matching rather than a YAML parser: Windows PowerShell 5.1 ships
# --- none. Every entry starts with `- name:`, but not every entry is an app
# --- with a checkout - `logs` is platform-owned and says so with `repo: null`
# --- - so an entry counts only once it names a repository.
$apps = @()
$entry = $null
foreach ($line in Get-Content $registry) {
    if ($line -match '^\s+-\s+name:\s*(\S+)') { $entry = $Matches[1] }
    elseif ($entry -and $line -match '^\s+repo:\s*(\S+)') {
        if ($Matches[1] -ne 'null') { $apps += $entry }
        $entry = $null
    }
}

$repos = @([pscustomobject]@{ Name = 'platform'; Path = $root }) +
         @($apps | ForEach-Object { [pscustomobject]@{ Name = $_; Path = Join-Path $root $_ } })

# --- No $ErrorActionPreference = 'Stop' here, on purpose. git writes progress
# --- to stderr, and 5.1 turns redirected stderr into terminating errors under
# --- 'Stop' (see docs/setup-local.md). Every git call below is judged by its
# --- exit code instead.
function Get-Git {
    param([string]$Path, [string[]]$Arguments)
    $out = & git -C $Path @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($out -join "`n").Trim()
}

$results = @()

foreach ($repo in $repos) {
    Write-Host "==> $($repo.Name)" -ForegroundColor Cyan

    if (-not (Test-Path (Join-Path $repo.Path '.git'))) {
        Write-Host '    not cloned here - skipped' -ForegroundColor DarkGray
        $results += [pscustomobject]@{ Repo = $repo.Name; Branch = '-'; Result = 'not cloned'; Ok = $true }
        continue
    }

    $branch = Get-Git $repo.Path @('rev-parse', '--abbrev-ref', 'HEAD')
    $before = Get-Git $repo.Path @('rev-parse', 'HEAD')
    $dirty = Get-Git $repo.Path @('status', '--porcelain')
    $upstream = Get-Git $repo.Path @('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}')

    $pull = -not $FetchOnly
    $reason = $null
    if ($branch -eq 'HEAD') { $pull = $false; $reason = 'detached HEAD - fetched only' }
    elseif (-not $upstream) { $pull = $false; $reason = 'no upstream - fetched only' }
    elseif ($dirty) { $pull = $false; $reason = 'uncommitted changes - fetched only' }

    if (-not $pull) {
        & git -C $repo.Path fetch --prune origin
        if ($LASTEXITCODE -ne 0) {
            $results += [pscustomobject]@{ Repo = $repo.Name; Branch = $branch; Result = 'FETCH FAILED'; Ok = $false }
            continue
        }
        if ($FetchOnly -and -not $reason) {
            $behind = Get-Git $repo.Path @('rev-list', '--count', 'HEAD..@{u}')
            $result = if ($behind -and $behind -ne '0') { "fetched; $behind behind $upstream" } else { 'fetched; up to date' }
            $results += [pscustomobject]@{ Repo = $repo.Name; Branch = $branch; Result = $result; Ok = $true }
        }
        else {
            Write-Host "    $reason" -ForegroundColor Yellow
            $results += [pscustomobject]@{ Repo = $repo.Name; Branch = $branch; Result = $reason; Ok = $false }
        }
        continue
    }

    & git -C $repo.Path pull --ff-only --prune
    if ($LASTEXITCODE -ne 0) {
        $results += [pscustomobject]@{ Repo = $repo.Name; Branch = $branch; Result = 'PULL REFUSED - diverged or failed, see above'; Ok = $false }
        continue
    }

    $after = Get-Git $repo.Path @('rev-parse', 'HEAD')
    if ($after -eq $before) { $result = 'up to date' }
    else {
        $count = Get-Git $repo.Path @('rev-list', '--count', "$before..$after")
        $result = "pulled $count commit(s)"
    }
    $results += [pscustomobject]@{ Repo = $repo.Name; Branch = $branch; Result = $result; Ok = $true }
}

Write-Host ''
Write-Host '==> Summary' -ForegroundColor Cyan
foreach ($r in $results) {
    $line = '    {0,-10} {1,-32} {2}' -f $r.Repo, $r.Branch, $r.Result
    if (-not $r.Ok) { $colour = 'Yellow' }
    elseif ($r.Branch -notin @('dev', 'main', '-')) { $colour = 'Yellow' }
    else { $colour = 'Green' }
    Write-Host $line -ForegroundColor $colour
}

$offBranch = @($results | Where-Object { $_.Branch -notin @('dev', 'main', '-') })
if ($offBranch) {
    Write-Host ''
    Write-Host '    A yellow branch is not dev or main: it is that branch that was updated,' -ForegroundColor DarkGray
    Write-Host '    not dev. Check it is the one you meant to be on.' -ForegroundColor DarkGray
}

if (@($results | Where-Object { -not $_.Ok }).Count -gt 0) { exit 1 }
exit 0

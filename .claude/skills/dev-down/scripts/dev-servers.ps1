#requires -Version 5
<#
.SYNOPSIS
    Finds the development servers running on this machine, grouped by the
    checkout they belong to, and stops the ones asked for.

.DESCRIPTION
    Shared by the dev-up and dev-down skills. A "server" is a uvicorn or a
    Vite process, plus whatever it was started from: the venv launcher, npm,
    and the `powershell -NoExit` pane a dev.ps1 opened for it.

    Each server is attributed to a checkout by walking its parent chain until
    some executable or command line names a path containing \venv\,
    \frontend\ or \node_modules\. What that cannot attribute - in practice a
    uvicorn --reload worker whose parents are gone, which is the system
    Python with a multiprocessing command line naming nothing (see the
    platform's docs/dev-ports.md) - is attributed by port instead, from the
    allocation in apps.yml, under the key "orphan:<app>".

.PARAMETER Platform
    The platform checkout, for apps.yml. Defaults to the first directory
    above -From that holds an apps.yml.

.PARAMETER From
    Where to start looking for the platform. Defaults to the current
    directory.

.PARAMETER Stop
    Keys from the listing (a checkout path, or orphan:<app>) to stop. Each
    server's whole process tree is killed, then the listing is re-taken and
    printed so the caller can see what is left.

.OUTPUTS
    JSON: one object per key, with the app it belongs to (when known), the
    ports it listens on, and the process ids involved.
#>
[CmdletBinding()]
param(
    [string]$Platform,
    [string]$From = (Get-Location).Path,
    [string[]]$Stop
)

$ErrorActionPreference = 'Stop'

function Find-Platform([string]$start) {
    $dir = Get-Item -LiteralPath $start
    while ($dir) {
        if (Test-Path (Join-Path $dir.FullName 'apps.yml')) { return $dir.FullName }
        $dir = $dir.Parent
    }
    return $null
}

# name -> backend port, read with a regex rather than a YAML parser: the file
# is flat enough, and PowerShell 5.1 ships no YAML module.
function Read-PortAllocation([string]$platformDir) {
    $slots = @{}
    if (-not $platformDir) { return $slots }
    $name = $null
    foreach ($line in Get-Content (Join-Path $platformDir 'apps.yml')) {
        if ($line -match '^\s*-\s*name:\s*(\S+)') { $name = $Matches[1] }
        elseif ($name -and $line -match '^\s+port:\s*(\d+)') {
            $backend = [int]$Matches[1]
            $slots[$backend] = $name
            $slots[5173 + ($backend - 8000)] = $name
            $name = $null
        }
    }
    return $slots
}

if (-not $Platform) { $Platform = Find-Platform $From }
$slots = Read-PortAllocation $Platform

$procs = @{}
foreach ($p in Get-CimInstance Win32_Process) { $procs[[int]$p.ProcessId] = $p }

# This script and everything above it - the shell that ran it, and the agent
# that ran the shell. Excluded from every group whatever the rules below say.
$self = @{}
$id = $PID
while ($procs.ContainsKey($id) -and -not $self.ContainsKey($id)) {
    $self[$id] = $true
    $id = [int]$procs[$id].ParentProcessId
}

function Get-Text($p) { "$($p.ExecutablePath) $($p.CommandLine)" }

$serverPattern = 'uvicorn|node_modules[\\/]vite[\\/]bin[\\/]vite\.js'
# No ':' inside the path, so a match cannot start at one path's drive letter
# and run on into the next path on the same command line.
$checkoutPattern = '([A-Za-z]:\\[^":]*?)\\(venv|frontend|node_modules)\\'

# A process worth killing along with the server it leads to. A powershell
# only counts when it was opened to host one command (-NoExit -Command), so
# an interactive shell somebody typed `uvicorn` into is left alone.
function Test-Hosting($p) {
    if ($p.Name -match '^(python|pythonw|node|uvicorn|npm|cmd)\.exe$') { return $true }
    if ($p.Name -match '^(powershell|pwsh)\.exe$' -and $p.CommandLine -match '-NoExit' -and $p.CommandLine -match '-Command') { return $true }
    return $false
}

$listening = @{}
foreach ($c in Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue) {
    $port = [int]$c.LocalPort
    if (($port -ge 8000 -and $port -le 8099) -or ($port -ge 5173 -and $port -le 5272)) {
        $listening[[int]$c.OwningProcess] = @($listening[[int]$c.OwningProcess]) + $port | Where-Object { $_ } | Sort-Object -Unique
    }
}

$candidates = @()
foreach ($p in $procs.Values) {
    # Only the server processes themselves: a shell or a grep whose command
    # line merely mentions uvicorn is not one. Their hosts are reached by the
    # walk up from here.
    if ($p.Name -notmatch '^(python|pythonw|node|uvicorn)\.exe$') { continue }
    $isServer = (Get-Text $p) -match $serverPattern
    $isListener = $listening.ContainsKey([int]$p.ProcessId)
    if ($isServer -or $isListener) { $candidates += $p }
}

$groups = @{}
foreach ($p in $candidates) {
    # Walk up: the chain is this process and every live ancestor. `seen`
    # guards against a recycled parent id pointing back into the chain.
    $chain = @($p)
    $seen = @{ [int]$p.ProcessId = $true }
    $cur = $p
    while ($procs.ContainsKey([int]$cur.ParentProcessId) -and -not $seen.ContainsKey([int]$cur.ParentProcessId)) {
        $cur = $procs[[int]$cur.ParentProcessId]
        $seen[[int]$cur.ProcessId] = $true
        $chain += $cur
    }

    $checkout = $null
    foreach ($q in $chain) {
        if ("$($q.ExecutablePath)" -match $checkoutPattern -or "$($q.CommandLine)" -match $checkoutPattern) {
            $checkout = $Matches[1]; break
        }
    }

    # Only the hosting prefix of the chain belongs to the server. Everything
    # above the first non-hosting ancestor - a bash, Claude Code itself,
    # Windows Terminal, explorer - is somebody else's and is never killed.
    $owned = @()
    foreach ($q in $chain) {
        if ((Test-Hosting $q) -and -not $self.ContainsKey([int]$q.ProcessId)) { $owned += $q } else { break }
    }
    if ($self.ContainsKey([int]$p.ProcessId)) { continue }
    if (-not $owned) { $owned = @($p) }
    $root = $owned[-1]

    $ports = @($listening[[int]$p.ProcessId] | Where-Object { $_ })
    if ($checkout) {
        $key = (Resolve-Path -LiteralPath $checkout -ErrorAction SilentlyContinue).Path
        if (-not $key) { $key = $checkout }
        $app = $null
    } else {
        $app = ($ports | ForEach-Object { $slots[$_] } | Where-Object { $_ } | Select-Object -First 1)
        if (-not $ports) { continue }   # a non-listening fragment with no owner: nothing to report
        $key = if ($app) { "orphan:$app" } else { 'orphan:unallocated' }
    }

    if (-not $groups.ContainsKey($key)) {
        $groups[$key] = [ordered]@{ key = $key; app = $app; ports = @(); roots = @(); pids = @() }
    }
    $g = $groups[$key]
    $g.ports = @($g.ports + $ports | Sort-Object -Unique)
    $g.roots = @($g.roots + [int]$root.ProcessId | Sort-Object -Unique)
    $g.pids = @($g.pids + ($owned | ForEach-Object { [int]$_.ProcessId }) | Sort-Object -Unique)
}

# A checkout's app is the slot its ports fall in, or failing that its folder
# name when that is a registered app.
foreach ($g in $groups.Values) {
    if (-not $g.app) {
        $g.app = ($g.ports | ForEach-Object { $slots[$_] } | Where-Object { $_ } | Select-Object -First 1)
        if (-not $g.app -and $g.key -notlike 'orphan:*') {
            $leaf = Split-Path $g.key -Leaf
            if ($slots.Values -contains $leaf) { $g.app = $leaf }
        }
    }
}

if ($Stop) {
    # Stop-Process and taskkill both end a process with exit code 1 or -1;
    # this is the only way to choose the code.
    Add-Type -Namespace DevServers -Name CleanExit -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)]
public static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
[DllImport("kernel32.dll", SetLastError = true)]
public static extern bool TerminateProcess(IntPtr handle, uint exitCode);
[DllImport("kernel32.dll")]
public static extern bool CloseHandle(IntPtr handle);
'@
    foreach ($key in $Stop) {
        $match = $groups.Keys | Where-Object { $_ -ieq $key }
        if (-not $match) { Write-Warning "Nothing running under '$key'."; continue }
        $g = $groups[$match]
        # A pane host is a powershell that dev.ps1 opened in Windows Terminal.
        # Everything below it goes first; then the host itself is ended with
        # exit code 0, because Windows Terminal closes a pane by itself only
        # when its shell exits cleanly - killed the ordinary way (code 1) the
        # pane stays open reading "process exited", and so does the window.
        # The window cannot be closed directly: it usually shares one
        # WindowsTerminal process with the session running this script.
        $hosts = @($g.roots | Where-Object { $procs[$_].Name -match '^(powershell|pwsh)\.exe$' })
        foreach ($id in $g.roots) {
            if ($hosts -contains $id) {
                Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" |
                    ForEach-Object { & taskkill.exe /PID $_.ProcessId /T /F 2>&1 | Out-Null }
            } else {
                # The tree kill reaches everything still parented.
                & taskkill.exe /PID $id /T /F 2>&1 | Out-Null
            }
        }
        # What the trees no longer reach, such as a reload worker whose
        # reloader has already gone.
        foreach ($id in $g.pids) {
            if ($hosts -notcontains $id) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
        }
        foreach ($id in $hosts) {
            $h = [DevServers.CleanExit]::OpenProcess(0x0001, $false, $id)   # PROCESS_TERMINATE
            if ($h -ne [IntPtr]::Zero) {
                [void][DevServers.CleanExit]::TerminateProcess($h, 0)
                [void][DevServers.CleanExit]::CloseHandle($h)
            }
        }
    }
    Start-Sleep -Seconds 2
    & $PSCommandPath -Platform $Platform -From $From
    return
}

ConvertTo-Json -InputObject @($groups.Values | Sort-Object { $_.key }) -Depth 4

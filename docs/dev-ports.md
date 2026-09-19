# Development ports, and freeing one that is stuck

Every app's development ports are derived from `apps.yml`, so they are a
box-wide allocation rather than a per-app preference:

| App | uvicorn | Vite |
| --- | --- | --- |
| `media` | 8000 | 5173 |
| `food` | 8001 | 5174 |
| `travel` | 8002 | 5175 |
| `art` | 8003 | 5176 |

uvicorn takes the app's registered `port`; Vite takes `5173 + (port - 8000)`.

**Do not reach for another port when one will not free.** Taking 8003 because
8002 is stuck silently takes `art`'s slot, and the collision surfaces later as
somebody else's app failing to bind for no visible reason. Every app's
`dev.ps1` aborts rather than falling back, for exactly this reason. Free the
port instead.

## A port that will not free, held by a process that does not exist

The symptom is a dev server refusing to start while the port is listening and
its owner appears to be gone:

```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen   # shows a listener
Get-Process -Id <that PID>                           # finds nothing
```

**What causes it.** With `--reload`, uvicorn runs a reloader parent and a
worker, and the worker inherits the listening socket. Killing the worker first,
or the parent first and then the worker, leaves the survivor holding a socket
nothing owns any more. Closing the terminal **pane** releases the whole tree
cleanly; killing a process inside it is what strands the socket.

**Why the obvious search misses it.** The worker is the *system* Python, not the
app's venv, and its command line is:

```
"...\Python313\python.exe" "-c" "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=NNNN, pipe_handle=NNN)" "--multiprocessing-fork"
```

The app's directory appears nowhere in it, so filtering processes on the
repository path finds the reloader and not the worker — which is how a process
that is plainly there reads as absent.

**How to find it.** Match the socket's creation time against process start
times; the worker was started in the same second.

```powershell
Get-NetTCPConnection -LocalPort 8001 | Select-Object CreationTime, OwningProcess
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } |
    Select-Object ProcessId, CreationDate, CommandLine | Sort-Object CreationDate
```

Stop that PID and the port frees.

## Testing whether a port is held needs the same address the server uses

Only an exact address-and-port match collides on Windows. Measured, not
recalled:

| Holder binds | Then binding | Result |
| --- | --- | --- |
| `127.0.0.1` | `0.0.0.0` | succeeds |
| `0.0.0.0` | `127.0.0.1` | succeeds |
| `127.0.0.1` | `127.0.0.1` | fails, `WinError 10048` |
| `0.0.0.0` | `0.0.0.0` | fails, `WinError 10048` |

**This is a property of which address the orphan happens to hold, not of
loopback.** A probe against `0.0.0.0` can succeed while the port is thoroughly
held and proves nothing. uvicorn binds `127.0.0.1` by default, so test that.
The corollary is worth knowing too: an orphan holding `0.0.0.0` does not stop
uvicorn starting at all, so this only bites when the stranded socket holds the
loopback address.

**A port guard should be address-agnostic even though the collision is not.**
All four `dev.ps1` scripts check `Get-NetTCPConnection -LocalPort <port> -State
Listen` with no address filter, while their uvicorn binds `127.0.0.1`. Those
come apart in the second row above: an orphan holding `0.0.0.0` makes the guard
abort even though uvicorn would have started fine.

That is correct, and the reason is the box-wide allocation rather than anything
about binding. The question a dev script asks is not "can I bind" but "is my
allocated slot free". A guard narrowed to `127.0.0.1` to match what the server
actually binds would let the app start alongside whatever else had taken its
port, which is quieter and worse than refusing.

## A worktree must not take the next free number

`media/worktree.ps1` allocates a worktree's port by starting at 8001 and
incrementing while something is listening. That was right when `media` was the
only app on the box and 8001 was empty space. It is wrong now: **8001, 8002 and
8003 are `food`, `travel` and `art`**, so the helper hands a media worktree
another app's registered port whenever that app simply is not running at the
time — and "not running" is the normal state of an app nobody is working on.

The probe makes it worse rather than better, because it tests whether a port is
*currently listening*, not whether it is *allocated*. An idle slot looks
identical to a free one.

Fixing it belongs to `media`, and the fix is to allocate above the registry
rather than into it — the reserved block ends at 8099, so a worktree should
start well clear of the apps, not at the next number after `media`.

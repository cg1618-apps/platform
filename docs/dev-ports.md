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
worker, and the worker inherits the listening socket. The worker outlives its
whole ancestry: terminating the hosting shell does **not** reap it, measured —
a `Stop-Process -Force` on the shell left the port held and two Python
processes alive.

**Shut the server down before closing the window.** Press Ctrl+C in the uvicorn
pane and wait for it to exit. Anything that kills the shell without letting it
signal its children strands the worker with the socket. Whether closing a
terminal *tab* is gentler depends on a console close event reaching the process
group, which is not worth relying on when Ctrl+C is unambiguous — and that path
has not been tested here, so this page does not claim it either way.

**Verify before restarting**, rather than finding out from a dev script whose
message scrolls away:

```powershell
Get-NetTCPConnection -LocalPort <port> -State Listen -ErrorAction SilentlyContinue
```

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

Fixing it belongs to `media`. So that a constant in one repository and a table
in another cannot disagree, **the floor is 8050**: apps keep `8000`-`8049`, and
every worktree allocates from `8050` upward within the schema's `8000`-`8099`
block. Four apps hold 8000-8003 today and 46 slots is more headroom than the
registry will plausibly need, so a worktree can never walk into an app's slot.

A worktree's Vite port follows the same derivation as an app's,
`5173 + (port - 8000)`, so a worktree backend on 8050 pairs with Vite on 5223.

### The frontend half of the same defect

`worktree.ps1` allocates no Vite port at all — it prints a uvicorn command and
nothing else — and two things in `media/frontend/vite.config.js` finish the
job:

- **`port: 5173` with no `strictPort`.** Vite silently auto-increments when
  5173 is busy, and the main tree holds 5173, so a worktree's Vite takes
  **5174, which is `food`'s registered port**, and reports success. Quieter
  than the backend case, because there is not even a deliberate probe to be
  wrong about — it is a default.
- **`proxy` hard-coded to `http://127.0.0.1:8000`** for `/api` and `/static`.
  A worktree running its own uvicorn on another port still gets a frontend
  talking to the **main tree's** backend, against the main tree's database. It
  looks like it works, which is worse than a bind failure: a bind failure is
  loud, and this shows plausible data from the wrong database.

So a ports fix that does not also cover the proxy target leaves the worktree
only appearing to be isolated.

**`media` is the only app missing `strictPort`.** `food`, `travel` and `art`
all set it. That is worth stating because `media` is the reference
implementation, and the reference is not uniformly ahead of the apps that
copied it — here the three newer apps are right and the reference is wrong.

**None of this is enforced by a test.** `media` has no Pester and no
`*.Tests.ps1`; its `tests/` is pytest only, so a fix to `worktree.ps1` is
unproven unless Pester is adopted, which is a larger decision than the fix.
Saying so is better than implying coverage that does not exist.

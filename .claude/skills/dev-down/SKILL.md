---
name: dev-down
description: Stop and clean up the development servers of the cg1618 app this session is in - every uvicorn, reload worker and Vite it has running, including stale leftovers and the Windows Terminal panes dev.ps1 opened - and free its ports. Other apps' servers are left alone unless the user agrees to stop them too. Use whenever the user wants the app's local servers gone - "close the dev server", "stop the app", "kill the servers", "clean up dev", "free the port", "port 8000 is stuck", "shut it down" - or before restarting a dev server that will not bind. Not for the shared PostgreSQL, Docker, or anything on the box.
---

# dev-down

Stop every development server belonging to this session's app checkout and
leave its ports free. Servers belonging to anything else - another app, or
another checkout of this app - are listed and left running unless the user
says otherwise.

The work is done by `scripts/dev-servers.ps1`, next to this file. It finds
uvicorn and Vite processes, walks up each one's parent chain to the pane that
hosts it, and attributes it to a checkout by the paths on those command lines.
It exists because the obvious approaches miss things: with `--reload`,
uvicorn's worker is the *system* Python with a command line that names no
path at all, and it survives its window being closed while still holding the
port (the platform's `docs/dev-ports.md` has the measurement). The script
catches it through its parents while they live, and through the `apps.yml`
port allocation, as `orphan:<app>`, when they do not.

It never touches its own ancestors, which is to say this agent and its shell,
and never a shell that was not opened just to host a server.

## 1. Work out which checkout this is

`git rev-parse --show-toplevel` from the working directory. If the session is
in the platform repository rather than an app, ask which app is meant - unless
the user asked for every server, in which case go straight to step 2 and treat
all groups as requested.

## 2. List what is running

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <this skill's base directory>/scripts/dev-servers.ps1 -From <checkout>
```

One JSON object per group: `key` (a checkout path, or `orphan:<app>`), `app`,
the `ports` it listens on, and the process ids.

Sort the groups into two piles:

- **Mine**: the group whose `key` is this checkout, plus `orphan:<this app>`
  when this is the app's main checkout (an orphan on the app's registered
  port is a leftover of the app's own server). A group with no ports is still
  mine - a stale reloader is exactly what cleaning up is for.
- **Others**: everything else, including worktrees of this same app. A
  worktree is a separate checkout, and possibly somebody else's running
  session.

## 3. Ask about the others, if there are any

When the others pile is empty, say nothing about it and go on.

Otherwise ask before stopping - one multi-select question listing each group
by app, folder and ports, so the user can tick any of them. **The default is
to leave them all running**, and nothing is stopped without a tick: they may
belong to another session that is mid-review. Skip the question when the
user's request already answered it ("stop everything", "all the dev servers",
"food's too").

## 4. Stop, and check

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <dev-servers.ps1> -From <checkout> -Stop '<key>','<key>'
```

It kills each group's process trees, then prints the listing again. Read that
second listing rather than assuming: a stopped key that is still there, or a
port still listening, means something survived. Run it once more; if the port
is still held, report the PID from `Get-NetTCPConnection -LocalPort <port>
-State Listen` rather than escalating further.

Windows Terminal panes that `dev.ps1` opened close as their shells are
killed. That is expected.

## 5. Report

One or two lines: which ports are now free, anything stale that was cleaned up
(a leftover reloader, an orphaned worker), and what was deliberately left
running - other apps' servers and, always, the shared `cg1618-dev-db`
container and Docker Desktop. Those are shared by every app on the machine, so
this skill does not stop them. The user can stop the database with the
platform's `dev-db.cmd -Down` if they want it gone.

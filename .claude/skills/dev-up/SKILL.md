---
name: dev-up
description: Start the development servers (uvicorn + Vite) for the cg1618 app this session is in - media, food, travel or art - including Docker Desktop and the shared dev PostgreSQL when they are down, and confirm the app answers before reporting its URLs. Use whenever the user wants to see, open, run, start, launch or check the app locally - "open dev server", "start the app", "let me look at it", "run it so I can check", "bring the dev env up", "is the app running?" - even when they do not say "server". Not for production or the box; not for running tests.
---

# dev-up

Bring the current app's development servers up so the user can look at it in a
browser, and say where.

Every app on this machine has its own `dev.ps1` at the root of its checkout.
**Run that rather than starting uvicorn and Vite yourself.** It carries the
app's own guards (a stale backend holding the port, a native PostgreSQL
shadowing the container), starts the shared database, opens a Windows
Terminal window with uvicorn and Vite side by side, and waits until the
backend answers. The window also means the servers outlive this session and
the user can read their logs, which a background process of yours would hide.

The servers are found and stopped by a script that lives with the `dev-down`
skill: `<this skill's base directory>/../dev-down/scripts/dev-servers.ps1`.
Call it `dev-servers.ps1` below.

## 1. Work out which checkout this is

`git rev-parse --show-toplevel` from the working directory. It has to contain
a `dev.ps1`; if it does not - most often because the session is in the
platform repository itself - ask the user which app they mean.

A worktree (a folder like `media_<topic>`) is its own checkout, but its
`dev.ps1` binds the same ports as the app's main checkout. That is handled in
step 2.

## 2. See what is already running

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <dev-servers.ps1> -From <checkout>
```

It prints one group per checkout (or `orphan:<app>` for a stranded uvicorn
worker that can only be identified by the port it holds), with the ports each
one listens on.

- **This checkout is already up, on both its ports** → do not start a second
  copy; go to step 5 and just confirm and report it.
- **This checkout is half up** (one port only, or a stale reloader with no
  port) or **`orphan:<this app>` holds this app's port** → those are this
  app's leftovers. Stop them with `-Stop <key>` and continue; `dev.ps1` would
  otherwise refuse to start.
- **Another checkout holds this app's ports** (typically the main checkout
  when this is a worktree, or the other way round) → stop and ask the user
  whether to stop that one. Do not stop it on your own initiative; it may be
  somebody's running session.

Other apps' servers on their own ports are irrelevant here. Leave them alone
and do not mention them unless asked.

## 3. Make sure Docker and the database are running

`dev.ps1` brings up the shared database container, but it cannot start Docker
itself and fails with a message that reads like a broken database. And step 4
needs the database before `dev.ps1` runs. Check Docker first:

```powershell
docker info *> $null; $LASTEXITCODE
```

Non-zero → start it and wait (it can take a minute):

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
for ($i = 0; $i -lt 40; $i++) { docker info *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep 5 }
```

Then the database. It belongs to the platform, not to the app: the compose
file is in the platform checkout, the nearest directory above this checkout
holding `apps.yml`. `up -d` is idempotent, so `dev.ps1` repeating it later is
harmless.

```bash
docker compose -f <platform>/docker-compose.dev-db.yml up -d
until docker exec cg1618-dev-db pg_isready -q; do sleep 1; done
```

## 4. Bring the database schema up to date

Every app uses Alembic. A database behind the code fails on a missing column
the moment a page loads, which looks like a bug in the change being reviewed.

```bash
venv/Scripts/python.exe -m alembic current
venv/Scripts/python.exe -m alembic heads
```

- Same revision → nothing to do.
- `current` is behind and appears in `alembic history` → `alembic upgrade
  head`. This touches only this app's own database.
- `current` names a revision **this branch does not know** → the database is
  ahead, migrated by another branch. Do not downgrade or upgrade anything; tell
  the user which revision it is and stop. The platform `CLAUDE.md` explains why
  ("The database does not follow the branch").

## 5. Start, and confirm

When step 2 found nothing to reuse:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <checkout>\dev.ps1
```

It returns after printing `==> Ready: http://localhost:<vite port>/`, or a red
line saying the backend did not answer. On failure the explanation is in the
uvicorn pane of the window it opened, not in this output - say so, and run
`dev-servers.ps1` again to see which half is missing.

Then check both halves answer, rather than trusting the script's line:

```bash
curl -s -m 5 -o /dev/null -w "%{http_code}" http://localhost:<backend port>/<health path>
curl -s -m 5 -o /dev/null -w "%{http_code}" http://localhost:<vite port>/
```

The health path is `/api/health` for `media` and `travel`, `/health` for
`food` and `art`; ports are in the platform's `docs/dev-ports.md`.

**`media` also serves a built bundle on its backend port.** `:8000` shows
`frontend_dist/`, which changes only on `npm run build`. If `frontend/src`
has anything newer than `frontend_dist/index.html`, run `cd frontend && npm
run build` so the two ports agree - otherwise the user reviews a stale page
on `:8000` and reports a bug that is not there.

## 6. Report

Keep it short: the URLs that answer (Vite first, it hot-reloads), the branch
the checkout is on (that is what they are looking at), and anything this skill
had to do on the way - Docker started, a migration run, leftovers stopped, a
rebuild. If it failed, say which step and what the output said.

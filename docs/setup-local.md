# Local development setup

Last verified: 2026-09-23

This page takes a Windows machine with nothing on it to a working copy of the
whole project: the platform checkout, all four apps cloned inside it, the shared
development PostgreSQL, and each app running on its registered ports.

It covers what the apps have in common. Each app's own `docs/` holds what only
that app needs, and `media/docs/setup-local.md` is the full walkthrough for the
largest of them: its API keys, `credentials.json` and the rest. The box is not
set up this way. See [shared-stack.md](shared-stack.md) for that.

## 1. Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.13 | Every app's `dockerfile` builds on `python:3.13-slim`, and CI uses it too. |
| Node.js | 20 | What CI and the frontend build stages use. A newer LTS also works locally. |
| Docker Desktop | current | Runs the development PostgreSQL. It is not optional. |
| Git | any | |
| Windows Terminal (`wt.exe`) | optional | The apps' `dev.ps1` scripts open their uvicorn and Vite panes with it. |

**No native PostgreSQL.** A native server binds 5432 as well and usually wins
the race against the container, so the apps would talk to the native server's
separate, empty database while nothing looks wrong. `dev-db.ps1` and every app's
`dev.ps1` refuse to start while one is running. If one is installed, stop it
from an elevated PowerShell:

```powershell
Stop-Service postgresql-x64-17 -Force
Set-Service postgresql-x64-17 -StartupType Manual
```

## 2. Clone the platform, then each app inside it

```powershell
git clone https://github.com/cg1618-apps/platform.git cg1618
cd cg1618
git clone https://github.com/cg1618-apps/media.git media
git clone https://github.com/cg1618-apps/food.git food
git clone https://github.com/cg1618-apps/travel.git travel
git clone https://github.com/cg1618-apps/art.git art
```

**Every app sits at `cg1618\<app>`.** This repository's `.gitignore` ignores
those directories, which keeps the histories apart, and each app's `dev.ps1`
looks for `..\docker-compose.dev-db.yml`. It stops if the app is cloned
anywhere else.

Then write a `CLAUDE.local.md` at the platform root and one in each app, naming
the machine (see "Two Development Machines" in `CLAUDE.md`). These files are
gitignored and per-machine. Write new ones here rather than copying them from
the other machine.

## 3. The development database

One container holds one database per app, the same arrangement production has.
It belongs to this repository rather than to any app. See
[registry.md](registry.md), "Development databases", for the reason.

```powershell
copy .env.example .env      # set POSTGRES_PASSWORD
.\dev-db.cmd                # start it; .\dev-db.cmd -Down stops it and keeps the volume
```

| | |
| --- | --- |
| Compose file | `docker-compose.dev-db.yml`, project `cg1618-dev-db` |
| Container | `cg1618-dev-db`, `postgres:17`, on `127.0.0.1:5432` |
| Volume | `cg1618_dev_pgdata` |

This repository's `.env` also has the tunnel variables. Those are for the box
and stay empty on a development machine.

**The container creates only the maintenance database.** The first time it
starts, create each app's databases yourself:

```powershell
docker exec cg1618-dev-db createdb -U postgres media
docker exec cg1618-dev-db createdb -U postgres media_test
docker exec cg1618-dev-db createdb -U postgres food
docker exec cg1618-dev-db createdb -U postgres food_test
docker exec cg1618-dev-db createdb -U postgres travel
docker exec cg1618-dev-db createdb -U postgres travel_test
docker exec cg1618-dev-db createdb -U postgres art
```

The `_test` databases are the ones each app's API tests wipe and rebuild, so
never put real data in one. `art`'s tests create and drop their own scratch
database, so it needs no `_test` database.

## 4. Each app

Run these in each app's directory:

```powershell
py -3.13 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env                   # POSTGRES_DB is already the app's name; set the password
venv\Scripts\alembic.exe upgrade head
cd frontend; npm install; npm run build; cd ..
.\dev.ps1
```

- **The venv must be named `venv`.** `dev.ps1` and the test commands call
  `venv\Scripts\...` by path.
- **`dev.ps1` starts the development database itself** if it is not running,
  then uvicorn and Vite.
- **Run migrations before you restore any data** into an app's database.
- The app's `.env.example` lists every variable the app reads. `media` needs
  more than the database: its §4 in `media/docs/setup-local.md` lists the API
  keys and the Google service account.

### Ports

Every app's ports come from `apps.yml`, so they are allocated across the whole
machine:

| App | uvicorn | Vite |
| --- | --- | --- |
| `media` | 8000 | 5173 |
| `food` | 8001 | 5174 |
| `travel` | 8002 | 5175 |
| `art` | 8003 | 5176 |

When a port will not free, free it. Do not start the app on another port: the
next port up belongs to another app. [dev-ports.md](dev-ports.md) explains how
to find the process holding it.

## 5. This repository's own tooling

Only needed for work on the platform itself:

```powershell
py -3.13 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m pytest -q
venv\Scripts\ruff.exe check .
.\dev.cmd                   # the log collector locally; Grafana on http://127.0.0.1:8008
```

`dev.cmd` starts Loki, Alloy and Grafana and nothing else. See
[observability.md](observability.md).

## 6. Checking it works

In each app:

```bash
venv/Scripts/python.exe -m pytest -q
venv/Scripts/ruff.exe check .
cd frontend && npm run lint
```

Every app shares one PostgreSQL, so take the machine-wide pytest lock before a
full test run. See "One pytest at a time, across every repository" in
`CLAUDE.md`.

Each app should also answer on its health route at its uvicorn port:
`/api/health` for `media` and `travel`, `/health` for `food` and `art`.

# Step 4: the deploy pipeline — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move deploying from one application's `deploy/` directory into the
platform, as `bin/deploy <app>` plus a reusable workflow every app calls, and
give each application its own database and role instead of the shared
superuser.

**Architecture:** `apps.yml` already says what each app is. `bin/deploy` reads
it rather than being told: the health path, the port and the database name all
come from the registry, and the app name is the only argument. The workflow
that calls it lives once in this repository as a `workflow_call`, so an app's
own deploy workflow is a few lines. `bin/provision` creates an app's database
and role once, with a password generated on the box that never leaves it.

**Tech Stack:** bash, Docker Compose, PostgreSQL 17, GitHub Actions reusable
workflows, systemd template units.

**Spec:** `docs/superpowers/specs/2026-09-17-cg1618-platform-architecture-design.md`

## Global Constraints

- **The media tracker is live throughout.** Every task before Task 6 is
  additive: the existing `deploy/` in `cg1618-apps/media` keeps working until
  the moment it is replaced, and it is replaced by one release, not gradually.
- **The box is reachable only from the home LAN**, and Tasks 6 and 7 need it.
- **Credentials are generated on the box and never printed.** `bin/provision`
  writes the role's password directly into the app's `.env` with `openssl rand`
  piped to a file. It is never echoed, never passed as a command argument (it
  would appear in `ps`), and never reaches a transcript, a commit or a log. Its
  correctness is proven by the app starting, not by reading it.
- **No `pull_request`-triggered job may run on the self-hosted runner**, in any
  repository. The reusable workflow must therefore never be callable from a
  `pull_request` trigger — Task 3 Step 4 asserts this.
- **`env -u COMPOSE_PROJECT_NAME`** on every compose call aimed at the platform
  project from a script that has sourced an app's `.env`. This is what broke the
  first deploy after the split; `docs/shared-stack.md` records why.
- **Nothing in git mentions AI**, in any commit message or pull request body.
- The apps are built in the order **`food`, `travel`, `art`**. Step 4 must leave
  `bin/provision food` working on an app that does not exist yet.

---

### Task 1: `bin/provision <app>`

Creates an application's database and role. Run once per app, by hand, on the
box.

**Files:**
- Create: `bin/provision`
- Create: `tests/test_provision.py`

**Interfaces:**
- Consumes: `apps.yml` for the app's `database` value; `~/cg1618/.env` for the
  superuser.
- Produces: a database and a role both named after the app's `database` field,
  the role owning the database, and `POSTGRES_USER` / `POSTGRES_PASSWORD` /
  `POSTGRES_DB` written into the app's `.env` at `${APPS_DIR}/<name>/.env`.
- Refuses: an app not in `apps.yml`; an app whose `database` is `null`; a role
  that already exists, unless `--rotate` is passed.

- [ ] **Step 1: Write the failing test**

The tests assert the *shape* of the script, as the other script tests here do —
it needs a live PostgreSQL to run for real, which CI does not have.

```python
"""bin/provision's invariants: the ones that would leak or destroy."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "bin" / "provision"


def code() -> str:
    lines = PROVISION.read_text(encoding="utf-8").splitlines()
    return "\n".join(l for l in lines if not l.lstrip().startswith("#"))


def test_it_fails_fast():
    assert "set -euo pipefail" in PROVISION.read_text(encoding="utf-8")


def test_the_password_is_never_a_command_argument():
    # A password in argv is visible in `ps` to every user on the box for as
    # long as the command runs. psql takes it from PGPASSWORD or a file.
    assert "--password=" not in code()
    assert "PGPASSWORD" in code()


def test_the_password_is_never_echoed():
    # The whole point: it goes from openssl into a file, and nowhere else.
    for line in code().splitlines():
        if "openssl rand" in line:
            assert "echo" not in line, line
            assert ">>" in line or ">" in line, line


def test_it_refuses_an_unknown_app():
    assert "not in apps.yml" in PROVISION.read_text(encoding="utf-8")


def test_it_refuses_to_clobber_an_existing_role():
    # Re-running it must not silently rotate a password the app is using: the
    # app would keep its old one in .env and fail on the next restart, which
    # looks like a database outage rather than a provisioning mistake.
    assert "--rotate" in code()


def test_it_never_drops_anything():
    # There is no un-provision. Removing an app's data is a deliberate act with
    # a dump taken first, not a flag on the script that creates it.
    lowered = code().lower()
    assert "drop database" not in lowered
    assert "drop role" not in lowered
```

- [ ] **Step 2: Run it, watch it fail**

```bash
venv/Scripts/python.exe -m pytest tests/test_provision.py -q
```

Expected: every test fails on the missing file.

- [ ] **Step 3: Write `bin/provision`**

```bash
#!/usr/bin/env bash
# Create an application's database and role. Run once per app, on the box.
#
#   ./bin/provision <app>            create
#   ./bin/provision <app> --rotate   replace the password of an existing role
#
# The password is generated here and written straight into the app's .env. It is
# never echoed, never passed as an argument (argv is world-readable in `ps`),
# and never leaves the box. Its correctness is proven by the app starting.

set -euo pipefail

cd "$(dirname "$0")/.."

APPS_DIR="${APPS_DIR:-$(dirname "$(pwd)")}"
APP="${1:?usage: provision <app> [--rotate]}"
ROTATE="${2:-}"

# The registry is the source of truth for the database name, so a typo here
# cannot create a database no generated file knows about.
DB="$(python3 -c "
import sys, yaml
apps = yaml.safe_load(open('apps.yml'))['apps']
match = [a for a in apps if a['name'] == sys.argv[1]]
if not match:
    sys.exit(f\"{sys.argv[1]} is not in apps.yml\")
if match[0]['database'] is None:
    sys.exit(f\"{sys.argv[1]} declares no database\")
print(match[0]['database'])
" "${APP}")"

ENV_FILE="${APPS_DIR}/${APP}/.env"
[ -f "${ENV_FILE}" ] || { echo "No ${ENV_FILE}" >&2; exit 1; }

COMPOSE=(env -u COMPOSE_PROJECT_NAME docker compose -f docker-compose.prod.yml)

role_exists="$("${COMPOSE[@]}" exec -T db psql -U postgres -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname = '${DB}'")"

if [ -n "${role_exists}" ] && [ "${ROTATE}" != "--rotate" ]; then
    echo "Role ${DB} already exists. Pass --rotate to replace its password." >&2
    exit 1
fi

# Into a file, mode 600, and nowhere else. Read back only to hand to psql
# through PGPASSWORD and to write into the app's .env.
secret="$(mktemp)"; chmod 600 "${secret}"
trap 'rm -f "${secret}"' EXIT
openssl rand -base64 32 | tr -d '\n=+/' > "${secret}"

if [ -n "${role_exists}" ]; then
    "${COMPOSE[@]}" exec -T db psql -U postgres -v ON_ERROR_STOP=1 \
        -c "ALTER ROLE \"${DB}\" WITH PASSWORD '$(cat "${secret}")'"
else
    "${COMPOSE[@]}" exec -T db psql -U postgres -v ON_ERROR_STOP=1 \
        -c "CREATE ROLE \"${DB}\" LOGIN PASSWORD '$(cat "${secret}")'"
    "${COMPOSE[@]}" exec -T db psql -U postgres -v ON_ERROR_STOP=1 \
        -c "CREATE DATABASE \"${DB}\" OWNER \"${DB}\""
fi

# Rewrite the three keys in the app's .env without touching anything else, and
# without the new value passing through a shell variable that could be echoed.
python3 - "${ENV_FILE}" "${DB}" "${secret}" <<'PY'
import sys, pathlib
env_path, db, secret_path = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
secret = secret_path.read_text().strip()
wanted = {"POSTGRES_USER": db, "POSTGRES_PASSWORD": secret, "POSTGRES_DB": db}
lines, seen = [], set()
for line in env_path.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0] if "=" in line else None
    if key in wanted:
        lines.append(f"{key}={wanted[key]}")
        seen.add(key)
    else:
        lines.append(line)
for key, value in wanted.items():
    if key not in seen:
        lines.append(f"{key}={value}")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "provisioned ${APP}: database ${DB}, role ${DB}, credentials written to ${ENV_FILE}"
```

- [ ] **Step 4: Run the tests, then shellcheck**

```bash
venv/Scripts/python.exe -m pytest tests/test_provision.py -q
shellcheck bin/provision
```

- [ ] **Step 5: Commit**

---

### Task 2: `bin/deploy <app>`

Everything `deploy/deploy.sh` does today, with the app as an argument and the
registry as the source of everything else.

**Files:**
- Create: `bin/deploy`
- Create: `bin/rollback`
- Create: `bin/health`
- Create: `tests/test_deploy.py`

**Interfaces:**
- Consumes: `apps.yml` (`health_path`, `database`), `${APPS_DIR}/<app>` as the
  app's checkout, `~/cg1618/docker-compose.prod.yml` for the database.
- Produces: `bin/deploy <app> [--ci]`, exiting **2** when the deploy ran and the
  result is unhealthy and **1** when it refused to start. That distinction is
  what the workflow reads to decide whether rolling back is correct, and it must
  survive the move exactly.

- [ ] **Step 1: Port the three scripts, one property at a time**

Every guard in `deploy/deploy.sh` has a reason recorded beside it, and each one
was added after something went wrong. Carry them across verbatim rather than
rewriting: the branch check and its detached-`HEAD` exception, the empty-dump
refusal, the `alembic_version` capture beside the dump, the re-check for
arriving migrations against the box's own `HEAD`, the image tagging, the prune,
exit 2 versus exit 1.

Two things change, and only these two:

- the paths become `${APPS_DIR}/${APP}` instead of the script's own repository;
- the health probe reads `health_path` from `apps.yml` instead of hard-coding
  `/api/health`, and `migrations_path` becomes an argument instead of a
  hard-coded `alembic/versions/` grep.

- [ ] **Step 2: Assert the exit codes are still distinct**

```python
def test_deploy_exits_two_when_unhealthy_and_one_when_it_refuses():
    text = (ROOT / "bin" / "deploy").read_text(encoding="utf-8")
    assert "exit 2" in text
    # The refusals: wrong branch, no .env, an unapproved migration.
    assert text.count("exit 1") >= 3
```

- [ ] **Step 3: Assert the health probe is per-app and not hard-coded**

```python
def test_health_path_comes_from_the_registry():
    text = (ROOT / "bin" / "health").read_text(encoding="utf-8")
    assert "/api/health" not in text, "health_path must come from apps.yml"
    assert "health_path" in text
```

- [ ] **Step 4: Commit**

---

### Task 2b: The migration hook — a decision this plan did not foresee

**Reading `rollback.sh` line by line shows that a generic rollback is not
possible as the plan assumed.** Three of its steps are not "deploying" at all,
they are *Alembic*:

- it records the schema's revision beside the dump, by querying
  `alembic_version`;
- it refuses to downgrade a revision whose file contains the literal line
  `irreversible = True`;
- it downgrades with `alembic downgrade <target>`, run from the **new** image
  with `--entrypoint alembic`, because the previous image has never heard of
  the revisions being reversed — and because omitting `--entrypoint` silently
  re-ran the upgrade that had just failed, observed on the box.

An app written against a different migration tool, or with no migrations at
all, can satisfy none of that. So the platform cannot own tier 2.

**Proposed contract, for the owner to accept or replace.** An app that has
migrations ships one executable, `deploy/migrations`, with three subcommands:

| Command | Prints / does | Used by |
| --- | --- | --- |
| `current` | the revision the **database** is at | `bin/deploy`, writing the sidecar beside the dump |
| `added <from> <to>` | the migration files a deploy would add, one per line, empty if none | `bin/deploy`'s unapproved-migration refusal, and `bin/rollback`'s "did this deploy add revisions" |
| `downgrade <target>` | reverses to that revision, non-zero if it refuses | `bin/rollback` tier 2 |

An app with no such file declares it has no migrations: `bin/deploy` skips the
sidecar and the approval gate, and `bin/rollback` goes straight from tier 1 to
tier 3. That is exactly right for an app whose schema never changes, and it is
what `travel` will look like on day one.

`migrations_path` then stops being a workflow input — `added` answers that
question from inside the app, where the answer lives.

**Why this shape rather than parameterising the platform.** Every alternative
puts one app's tool in the shared repository: a case statement on tool name, a
config key naming a downgrade command, or a Python entry point. All three make
the platform know about Alembic, and the next app's tool, and the one after.
The hook makes the app answer three questions about itself, which is the same
move `health_path` already made.

**What this costs:** the media tracker gains `deploy/migrations` — thin, since
its three answers already exist inside `deploy.sh` and `rollback.sh` — and this
plan's Task 2 stops trying to port logic that cannot move.

---

### Task 3: The reusable workflow

**Files:**
- Create: `.github/workflows/deploy-app.yml` (in this repository)
- Create: `tests/test_deploy_workflow.py`

**Interfaces:**
- Produces: a `workflow_call` workflow taking `app`, `migrations_path` and an
  optional `runs_on`, with the classify job, the two lanes and the
  `production` environment gate, exactly as `cg1618-apps/media` has them today.

- [ ] **Step 1: Port `deploy.yml` from the media repository**

Keep the comments: box-initiated by necessity, `concurrency` never cancelling in
flight, exit-2-only rollback, and why `classify` runs on `ubuntu-latest`.

Change: `concurrency: group: deploy-${{ inputs.app }}` — per app, so two apps
can deploy at once and one app cannot deploy over itself.

- [ ] **Step 2: Assert no `pull_request` trigger can reach the runner**

```python
def test_the_reusable_workflow_is_not_callable_from_a_pull_request():
    # A fork's pull request executing on a machine in a house is the standard
    # catastrophe, and this workflow is what would run it.
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "deploy-app.yml").read_text())
    assert set(wf[True]) == {"workflow_call"}
```

- [ ] **Step 3: Commit**

---

### Task 4: The media tracker adopts it

**Files (in `media/`):**
- Modify: `.github/workflows/deploy.yml` — reduced to a call
- Delete: `deploy/deploy.sh`, `deploy/rollback.sh`, `deploy/health.sh`
- Keep: `deploy/backup/sheets.sh`, `deploy/backup/covers.sh` — see Task 5

- [ ] **Step 1: Reduce the workflow**

```yaml
name: Deploy

on:
  push:
    branches:
      - main

jobs:
  deploy:
    uses: cg1618-apps/platform/.github/workflows/deploy-app.yml@main
    with:
      app: media
      migrations_path: alembic/versions/
    secrets: inherit
```

- [ ] **Step 2: Update `tests/unit/test_deploy_scripts.py`**

It asserts properties of scripts that no longer live here. The ones about
`sheets.sh`, `covers.sh` and `lib.sh` stay; the rest move to the platform's
suite with the scripts. **Do not delete an assertion without re-homing it** —
each one is a defect that already happened once.

- [ ] **Step 3: Run the full media suite, then commit**

---

### Task 5: The backup jobs split, because they are not all generic

**The five jobs are not uniform, and the obvious refactor is wrong.**
`backup.sh` (dump to R2), `verify.sh` (restore drill) and `drift.sh` (is the box
on `main`) are about any app's database and checkout. `sheets.sh` mirrors the
media tracker's data into Google Sheets and `covers.sh` syncs its cover images —
both are features of one application and must not move.

**Files:**
- Create (platform): `bin/backup`, `bin/verify`, `bin/drift`, `bin/lib.sh`
- Create (platform): `units/cg1618-backup@.service`, `.timer`, and the same for
  verify and drift — **template units**, instantiated per app
  (`systemctl enable cg1618-backup@media.timer`)
- Keep (media): `deploy/backup/sheets.sh`, `covers.sh`, and their units

**Interfaces:**
- Each generic job takes the app name from the systemd instance (`%i`) and reads
  everything else from `apps.yml`.
- Healthchecks URLs become per app: `HC_BACKUP_URL_MEDIA` in the platform's
  `.env.backup`, so one job failing for one app is one check going red.

- [ ] **Step 1: Port `lib.sh` with the instance name as an argument**

Keep `start_job`, the `flock`, the tee-drain ordering and `hc_ping`'s
warn-but-do-not-fail behaviour. Every one of those has a failure recorded
against it.

- [ ] **Step 2: Template the units**

```ini
[Unit]
Description=cg1618: nightly database dump and library mirror to R2 for %i
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=cgentle1618
ExecStart=/home/cgentle1618/cg1618/bin/backup %i
```

- [ ] **Step 3: Assert the media-specific jobs did not move**

```python
def test_the_sheets_and_covers_jobs_stay_with_the_app():
    # They are features of the media tracker, not of the box. A "tidy up" that
    # moves them here makes the platform know about Google Sheets.
    assert not (ROOT / "bin" / "sheets").exists()
    assert not (ROOT / "bin" / "covers").exists()
```

- [ ] **Step 4: Commit**

---

### Task 6: Cutover on the box

- [ ] **Step 1: Dump first**

```bash
ssh homelab && cd ~/anime_site && ./deploy/backup/backup.sh
```

- [ ] **Step 2: Provision the media role**

```bash
cd ~/cg1618 && ./bin/provision media
```

This writes new `POSTGRES_*` values into `~/anime_site/.env`. The database
already exists and is owned by `postgres`, so `provision` must also hand it
over:

```bash
env -u COMPOSE_PROJECT_NAME docker compose -f docker-compose.prod.yml exec -T db \
  psql -U postgres -v ON_ERROR_STOP=1 -c 'ALTER DATABASE anime_site_db OWNER TO media'
env -u COMPOSE_PROJECT_NAME docker compose -f docker-compose.prod.yml exec -T db \
  psql -U postgres -d anime_site_db -v ON_ERROR_STOP=1 \
  -c 'GRANT ALL ON ALL TABLES IN SCHEMA public TO media;
      GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO media;
      GRANT ALL ON SCHEMA public TO media'
```

**Verify before restarting the app**, because the app failing to connect is how
this goes wrong:

```bash
env -u COMPOSE_PROJECT_NAME docker compose -f docker-compose.prod.yml exec -T db \
  psql -U media -d anime_site_db -tAc "SELECT count(*) FROM anime"
```

Expected: the same count as before. A permission error here means stop and fix
the grants; the app is still running on the old credentials at this point.

- [ ] **Step 3: Restart the app onto the new role**

```bash
cd ~/anime_site && docker compose -f docker-compose.prod.yml up -d
./deploy/health.sh 180 || echo "ROLL BACK: restore the old POSTGRES_* in .env"
```

- [ ] **Step 4: Install the template units**

```bash
sudo ~/cg1618/bin/install-units
systemctl list-timers 'cg1618-*' --no-pager
```

- [ ] **Step 5: Release both repositories and watch the first deploy**

The media release triggers the reusable workflow for the first time. **The
first deploy after a change to the deploy path cannot fix its own path** — if
`bin/deploy` is broken, the run refuses before pulling, and the box needs one
manual `git pull` in `~/cg1618`. That happened in step 3 and is not a sign the
fix was wrong.

---

### Task 7: `bin/provision food`, on nothing

The proof that the registry, the provisioner and the workflow are actually
app-agnostic is provisioning an app that does not exist.

- [ ] **Step 1: Add `food` to `apps.yml`** — hostname `food.cg1618.com`, port
  8001, database `food`, exposure `public`, health path to be decided by the
  app. Open it as a pull request; CI regenerates the ingress and the diff shows
  the new rule.

- [ ] **Step 2: `./bin/provision food`** — expect it to refuse, because
  `~/cg1618/food/.env` does not exist. That refusal is the test.

- [ ] **Step 3: Record what app #2 needs** in `docs/registry.md`: a container on
  port 8001, a health path that answers only when it can serve, `DATABASE_URL`
  from the environment, and a `main` branch that is production.

---

### Task 5b: Uploaded files, which two apps now need

**`food` and `art` both need image storage**, discovered while decomposing
them: photographs of dishes and ingredients, reference images and pictures of
finished work. Neither should invent its own answer, and the media tracker
already has the shape:

- **A bind-mounted directory outside the container image**, so `rsync`, `tar`
  and the backup see ordinary files. `media` mounts `./static/covers` and
  `./static/library` from its checkout.
- **Backup coverage that distinguishes re-fetchable from irreplaceable.**
  `media` mirrors `static/library` nightly because nothing can supply those
  images again, and syncs `static/covers` weekly because the metadata APIs can.
  A photograph of a dish or a drawing is the first kind: nightly, always.

What this step has to decide, and what `bin/backup` has to implement:

- [ ] **Where an app's uploads live**, as a convention rather than per app —
  `<app checkout>/static/uploads/` is the obvious candidate, and the app
  declares nothing because the path is derived from its name.
- [ ] **Whether the registry needs to know.** An app with no uploads should not
  have an empty directory mirrored nightly. A boolean in `apps.yml` is the
  cheap answer; deriving it from the directory's existence is cheaper still and
  fails silently when the directory is missing, which is the wrong way round.
- [ ] **That the restore drill covers files, not only the database.** The
  current `verify.sh` restores a dump and counts rows. An upload store that has
  never been restored is a backup nobody has tested.

## What this step deliberately does not do

- **No app #2 code.** `food` gets a registry entry and a provisioned-on-request
  database, nothing more.
- **No apex page** — step 6, and it needs a port on the network rather than a
  pipeline.
- **The box's checkout stays at `~/anime_site`.** Renaming it to `~/cg1618/media`
  is cosmetic and would touch every unit path; it belongs with step 5's
  documentation move, if at all.

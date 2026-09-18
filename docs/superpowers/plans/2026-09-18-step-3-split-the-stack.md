# Step 3: split the running stack — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `db` and `cloudflared` out of the media tracker's stack and into
this repository, leaving `media` with only its `app` service joined to a shared
network — without losing the database, the tunnel, the nightly backup or the
ability to roll the whole thing back within minutes.

**Architecture:** The platform owns a compose project holding PostgreSQL and
the Cloudflare Tunnel, on a docker network every application joins. PostgreSQL
keeps the network alias **`db`**, which is the hostname the media app already
uses, so no application configuration changes. The tunnel's ingress stops being
a hand-written file in the app repo and becomes generated from `apps.yml`, with
CI failing on drift — which is also what carries the guard that
`tests/unit/test_prod_compose.py` provides today.

**Tech Stack:** Docker Compose (two projects, one external network), PostgreSQL
17, cloudflared, systemd timers, bash, Python 3.13 for the generator.

**Spec:** `docs/superpowers/specs/2026-09-17-cg1618-platform-architecture-design.md`

## Global Constraints

- **This is the only step that restructures live production.** `media.cg1618.com`
  is down for the cutover window in Task 7. Everything before Task 7 is
  preparation that changes nothing on the box.
- **The box is `homelab`, `10.45.216.243`, reachable only from the home LAN.**
  Do not begin unless the whole step can be finished in this session.
- **The database volume is renamed, not reused.** Compose prefixes volume names
  with the project, so `pgdata` under project `media` is `media_pgdata`. It
  becomes the platform's, holding one database per app, and a volume called
  `media_pgdata` full of other apps' data would be a lie. It moves by
  **dump and restore**, and the old volume is left untouched as the way back.
- **The app's `.env` is not edited in this step.** PostgreSQL keeps the alias
  `db`, so the connection string the app already has keeps resolving. A
  per-app role and database — the spec's "one database and one role per app" —
  arrives with `bin/provision` in step 4.
- **No `pull_request`-triggered job may run on the self-hosted runner**, in
  either repository.
- **Nothing in git mentions AI**, in any commit message or pull request body.
- Two repositories change, so **two pull requests**, and they must land in the
  order Task 7 uses them. They are not a stacked pair — neither branch contains
  the other's code — but the box must not pull one without the other, which is
  what the cutover window is for.

---

### Task 1: Record the state the rollback returns to

Nothing here changes anything. It produces the evidence that says whether the
cutover worked, and the exact commands that undo it.

**Files:**
- Create (on the box): `~/pre_split_state.txt`

**Interfaces:**
- Produces: row counts, volume name, image ids and revisions, captured before
  anything moves. Task 7 compares against these.

- [ ] **Step 1: Take a dump outside the deploy path**

```bash
ssh homelab
cd ~/anime_site && ./deploy/backup/backup.sh
ls -lt ~/backups | head -3
```

The nightly job ships to R2 as well, and this is the same script, so a clean run
here means the offsite copy is current too.

- [ ] **Step 2: Capture what "unchanged" will mean**

```bash
ssh homelab
cd ~/anime_site
{
  echo "git: $(git rev-parse HEAD)"
  echo "volume: $(docker volume ls --format '{{.Name}}' | grep pgdata)"
  docker compose -f docker-compose.prod.yml ps --format '{{.Name}} {{.Image}}'
  docker exec media-db-1 psql -U postgres -d anime_site_db -tAc \
    "SELECT 'anime=' || (SELECT count(*) FROM anime)
          || ' media=' || (SELECT count(*) FROM media)
          || ' users=' || (SELECT count(*) FROM users)
          || ' rev='   || (SELECT version_num FROM alembic_version)"
  docker exec media-db-1 psql -U postgres -tAc \
    "SELECT datname FROM pg_database WHERE datistemplate = false"
} | tee ~/pre_split_state.txt
```

Expected, from the state as this plan is written: `anime=837 media=2085`,
revision `s1e2asonalix`, volume `media_pgdata`, database `anime_site_db`. Read
the actual numbers from the box rather than trusting these — they are what the
comparison is against.

- [ ] **Step 3: Write the way back, before it is needed**

The rollback is: put the old compose file back, bring the old project up, and
the old volume is still there with the data in it.

```bash
# On the box, if the cutover goes wrong at any point in Task 7:
cd ~/anime_site
git checkout -- docker-compose.prod.yml          # or: git reset --hard <pre-split sha>
docker compose -f ~/cg1618/docker-compose.prod.yml down    # stop the new stack
docker compose -f docker-compose.prod.yml up -d            # the old three services
./deploy/health.sh 180
```

Nothing in Task 7 deletes `media_pgdata`, removes the old compose file from
git history, or changes the app's `.env`, which is what keeps this a three
command recovery. **Confirm you can read this back before starting Task 7.**

---

### Task 2: The platform's compose project

**Files:**
- Create: `docker-compose.prod.yml` (in this repository)
- Create: `.env.example`

**Interfaces:**
- Produces: a compose project named `cg1618` running `db` and `cloudflared`, on
  an external network `cg1618`, with PostgreSQL carrying the network aliases
  `db` and `postgres`, and a volume `cg1618_pgdata`.
- Consumes: `cloudflared/config.yml` generated by Task 3.

- [ ] **Step 1: Write `docker-compose.prod.yml`**

```yaml
# The shared half of the box: one PostgreSQL and one Cloudflare Tunnel, for
# every application. Each app runs its own compose project holding only its own
# service, and joins the `cg1618` network declared here.
#
# Run from this directory, which is where .env is loaded from:
#   docker compose -f docker-compose.prod.yml <command>

services:
  db:
    image: postgres:17
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      cg1618:
        # `db` is what every application already connects to, and keeping it
        # means no app's configuration changes when its database moves here.
        # `postgres` is the name a new app would reach for; both resolve.
        aliases:
          - db
          - postgres
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    # --no-autoupdate: the image is the unit of upgrade, and an in-place
    # self-update would restart the tunnel outside anyone's knowledge.
    command: tunnel --no-autoupdate --config /etc/cloudflared/config.yml run ${TUNNEL_ID}
    volumes:
      - ./cloudflared/config.yml:/etc/cloudflared/config.yml:ro
      - ${CLOUDFLARED_CREDENTIALS}:/etc/cloudflared/credentials.json:ro
    networks:
      - cg1618
    # No depends_on for the apps: they are separate compose projects and
    # compose cannot order across them. cloudflared answers 502 for a hostname
    # whose service is not up yet, and recovers on its own when it is - which
    # is the correct behaviour for a tunnel serving several apps independently.

volumes:
  pgdata:

networks:
  cg1618:
    name: cg1618
```

- [ ] **Step 2: Write `.env.example`**

```bash
# The platform's own environment. This is NOT an application's .env: it holds
# the PostgreSQL superuser and the tunnel's identity, and no application
# container is ever given it.
#
# Compose loads this directory's .env because the compose file lives here.
COMPOSE_PROJECT_NAME=cg1618

# PostgreSQL superuser. Each app gets its own database and role; this is the
# account that creates them.
POSTGRES_USER=postgres
POSTGRES_PASSWORD=
# The maintenance database the container initialises. App databases are created
# beside it.
POSTGRES_DB=postgres

# The Cloudflare Tunnel. TUNNEL_ID is not a secret; the credentials file is,
# and this names an absolute path to it on the box.
TUNNEL_ID=
CLOUDFLARED_CREDENTIALS=/home/cgentle1618/.cloudflared/<tunnel-id>.json
```

- [ ] **Step 3: Verify the compose file parses and resolves nothing by accident**

```bash
cd /c/Users/cgent/Documents/cg1618
docker compose -f docker-compose.prod.yml config >/dev/null && echo "parses"
```

On a development machine with no platform `.env`, expect warnings about unset
variables — that is correct here and is why Task 7 does the real check on the
box.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.prod.yml .env.example
git commit -m "feat: the shared stack - one PostgreSQL and one tunnel"
```

---

### Task 3: Generate the ingress from `apps.yml`

The ingress stops being hand-written. This is also where the guard that
`tests/unit/test_prod_compose.py` provides today comes across: that test is the
only thing standing between `journal.cg1618.com` and an accidental public route,
and moving the file without it would quietly delete the protection.

**Files:**
- Create: `bin/generate_ingress.py`
- Create: `cloudflared/config.yml` (generated, committed)
- Create: `tests/test_generate_ingress.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `apps.yml`, `bin/validate_apps.py`.
- Produces: `render(registry: dict) -> str`, the exact file contents;
  `main(argv=None) -> int` writing `cloudflared/config.yml`, and `--check`
  returning 1 when the committed file differs from what the registry implies.
  An app's service URL is `http://{name}-app:{port}`.

- [ ] **Step 1: Write the failing test**

```python
"""The ingress is derived from the registry, never hand-edited."""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

from generate_ingress import render  # noqa: E402

REGISTRY = yaml.safe_load((ROOT / "apps.yml").read_text(encoding="utf-8"))


def test_the_committed_file_matches_the_registry():
    committed = (ROOT / "cloudflared" / "config.yml").read_text(encoding="utf-8")
    assert committed == render(REGISTRY)


def test_every_app_is_routed_to_its_own_service():
    out = yaml.safe_load(render(REGISTRY))
    rules = {r["hostname"]: r["service"] for r in out["ingress"] if "hostname" in r}
    assert rules["media.cg1618.com"] == "http://media-app:8000"


def test_the_catch_all_is_last():
    # cloudflared refuses to start without it, and it must be the final rule.
    out = yaml.safe_load(render(REGISTRY))
    assert out["ingress"][-1] == {"service": "http_status:404"}
    assert all("hostname" in r for r in out["ingress"][:-1])


def test_a_lan_only_app_is_not_routed():
    # The tunnel is public ingress. lan-only means exactly "no rule here".
    registry = {"apps": [
        {"name": "media", "hostname": "media.cg1618.com", "port": 8000,
         "database": "media", "repo": "git@github.com:cg1618-apps/media.git",
         "exposure": "public", "health_path": "/api/health", "description": "x"},
        {"name": "money", "hostname": "money.cg1618.com", "port": 8001,
         "database": "money", "repo": "git@github.com:cg1618-apps/money.git",
         "exposure": "lan-only", "health_path": "/health", "description": "x"},
    ]}
    out = yaml.safe_load(render(registry))
    hostnames = [r.get("hostname") for r in out["ingress"]]
    assert "media.cg1618.com" in hostnames
    assert "money.cg1618.com" not in hostnames


def test_a_cloudflare_access_app_is_routed_and_marked():
    # Access is enforced by Cloudflare in front of the tunnel, so the rule
    # exists - but it must be visibly different in the file a human reads.
    registry = {"apps": [
        {"name": "journal", "hostname": "journal.cg1618.com", "port": 8002,
         "database": "journal", "repo": "git@github.com:cg1618-apps/journal.git",
         "exposure": "cloudflare-access", "health_path": "/health",
         "description": "x"},
    ]}
    rendered = render(registry)
    assert "journal.cg1618.com" in rendered
    assert "cloudflare-access" in rendered
```

- [ ] **Step 2: Run it and watch it fail**

```bash
venv/Scripts/python.exe -m pytest tests/test_generate_ingress.py -v
```

Expected: `ModuleNotFoundError: No module named 'generate_ingress'`.

- [ ] **Step 3: Write the generator**

```python
#!/usr/bin/env python3
"""Render the Cloudflare Tunnel ingress from apps.yml.

Hand-editing this file is how a hostname ends up routed that nobody decided to
route. The registry is where an app's exposure is decided - and where
bin/validate_apps.py refuses `public` for journal, health and money - so the
ingress is derived from it and CI fails if the committed output has drifted.

The generated file is committed rather than built at deploy time, because the
ingress that will be served is then visible in the pull request diff, where a
person reads it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "apps.yml"
OUTPUT = ROOT / "cloudflared" / "config.yml"

HEADER = """\
# GENERATED FROM apps.yml BY bin/generate_ingress.py - DO NOT EDIT.
#
# Regenerate with `python bin/generate_ingress.py`; CI fails if this file and
# apps.yml disagree. Add a hostname by adding its app to apps.yml, which is
# also where exposure is decided and where journal, health and money are
# refused `public`.
#
# The tunnel's id is NOT here. It is passed on the command line from TUNNEL_ID
# in the platform .env, which keeps this file static and committable. The id is
# not a secret either way; the credentials JSON is, and it is mounted read-only
# from a path the .env names.

credentials-file: /etc/cloudflared/credentials.json

ingress:
"""


def render(registry: dict) -> str:
    """Return the full contents of cloudflared/config.yml."""
    lines = [HEADER]
    for app in registry["apps"]:
        # lan-only means no public ingress rule at all. The tunnel IS the
        # public path, so omitting the rule is the whole implementation.
        if app["exposure"] == "lan-only":
            continue
        if app["exposure"] == "cloudflare-access":
            lines.append(
                f"  # {app['name']}: cloudflare-access - Cloudflare enforces\n"
                f"  # authentication in front of this rule.\n"
            )
        lines.append(
            f"  - hostname: {app['hostname']}\n"
            f"    service: http://{app['name']}-app:{app['port']}\n"
        )
    lines.append(
        "\n  # Required catch-all. cloudflared refuses to start without it,\n"
        "  # and it must be the last rule.\n"
        "  - service: http_status:404\n"
    )
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    rendered = render(registry)

    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != rendered:
            print(
                f"{OUTPUT.relative_to(ROOT)} does not match apps.yml. "
                f"Run `python bin/generate_ingress.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the file and run the tests**

```bash
venv/Scripts/python.exe bin/generate_ingress.py
venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: `wrote cloudflared/config.yml`, then all tests pass.

- [ ] **Step 5: Prove the drift check bites**

```bash
venv/Scripts/python.exe bin/generate_ingress.py --check; echo "clean exit=$?"     # 0
printf '\n# hand edit\n' >> cloudflared/config.yml
venv/Scripts/python.exe bin/generate_ingress.py --check; echo "drifted exit=$?"   # 1
venv/Scripts/python.exe bin/generate_ingress.py                                   # regenerate
venv/Scripts/python.exe bin/generate_ingress.py --check; echo "clean again exit=$?"
```

- [ ] **Step 6: Add the check to CI**

In `.github/workflows/ci.yml`, after "Validate the registry":

```yaml
      - name: Check the generated ingress matches the registry
        run: python bin/generate_ingress.py --check
```

- [ ] **Step 7: Commit**

```bash
git add bin/generate_ingress.py cloudflared/config.yml tests/test_generate_ingress.py .github/workflows/ci.yml
git commit -m "feat: generate the tunnel ingress from the registry"
```

---

### Task 4: Reduce the media stack to its own service

**Files (in `media/`):**
- Modify: `docker-compose.prod.yml`
- Modify: `tests/unit/test_prod_compose.py`
- Delete: `deploy/cloudflared/config.yml`

**Interfaces:**
- Consumes: the `cg1618` network and the `db` alias from Task 2.
- Produces: a compose project holding one service, `app`, reachable on the
  shared network as `media-app`.

- [ ] **Step 1: Rewrite `docker-compose.prod.yml`**

Keep every comment that still applies — the `image:` naming rationale, the
healthcheck's `/api/health` reasoning, the generous `start_period`, the bind
mount note. Replace the file's body with:

```yaml
services:
  app:
    build:
      context: .
      dockerfile: dockerfile
    image: media-app:local
    restart: unless-stopped
    env_file:
      - .env
    environment:
      PORT: 8000
    volumes:
      - ./static/covers:/app/static/covers
      - ./static/library:/app/static/library
    networks:
      cg1618:
        # The tunnel routes media.cg1618.com to http://media-app:8000, and that
        # name is generated from apps.yml in the platform repository. It is not
        # free to change here.
        aliases:
          - media-app
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    # No depends_on: PostgreSQL belongs to the platform's compose project and
    # compose cannot order across projects. `restart: unless-stopped` is what
    # covers a cold boot - the container exits when alembic cannot reach the
    # database and is restarted until it can. Bring the platform stack up
    # first and this never happens; after a power cut it may happen a few
    # times, which is noise in the log rather than a failure.

networks:
  cg1618:
    external: true
```

- [ ] **Step 2: Rewrite the compose invariants test**

The three-service assertions are now false, and the ingress assertions have
moved to the platform repository. What is still this repository's business:

```python
def test_the_only_service_is_the_app(compose):
    # db and cloudflared belong to cg1618-apps/platform. An app repository
    # that grows a database service again is one that has stopped sharing the
    # box's PostgreSQL, which is a decision, not an edit.
    assert set(compose["services"]) == {"app"}


def test_the_app_publishes_no_port(compose):
    # The tunnel is the only ingress. A published port bypasses Cloudflare.
    assert "ports" not in compose["services"]["app"]


def test_the_app_joins_the_shared_network_as_media_app(compose):
    # This alias is what the generated ingress routes to. If it changes here
    # and not in apps.yml, the tunnel 502s on media.cg1618.com.
    assert compose["services"]["app"]["networks"]["cg1618"]["aliases"] == ["media-app"]
    assert compose["networks"]["cg1618"]["external"] is True


def test_the_app_restarts_unless_stopped(compose):
    # Load-bearing since depends_on went away with the database: this is the
    # only thing that recovers the app when it starts before PostgreSQL.
    assert compose["services"]["app"]["restart"] == "unless-stopped"
```

Delete the parametrised three-service tests and the ingress test, and update the
module docstring to say the ingress guard now lives in the platform repository,
naming it.

- [ ] **Step 3: Delete the hand-written ingress**

```bash
git rm deploy/cloudflared/config.yml
```

- [ ] **Step 4: Run the media suite**

```bash
cd /c/Users/cgent/Documents/cg1618/media
LOCK=/c/Users/cgent/AppData/Local/Temp/anime_site_pytest.lock
until mkdir "$LOCK" 2>/dev/null; do sleep 10; done
venv/Scripts/python.exe -m pytest -q; rc=$?
rmdir "$LOCK"; exit $rc
```

Expected: pass. ~5.5 minutes; it is the only way to know nothing else read that
compose file.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.prod.yml tests/unit/test_prod_compose.py deploy/cloudflared/config.yml
git commit -m "refactor: the app is the only service this repository runs"
```

---

### Task 5: Teach the scripts where the database now lives

`deploy.sh`, `rollback.sh` and `deploy/backup/lib.sh` all reach PostgreSQL
through `docker compose -f docker-compose.prod.yml exec db`, which stops
resolving the moment `db` leaves that file. The full parameterised `bin/deploy`
is step 4; this task is the minimum that keeps dumps, rollbacks and the nightly
backup working in between.

**Files (in `media/`):**
- Modify: `deploy/deploy.sh`
- Modify: `deploy/rollback.sh`
- Modify: `deploy/backup/lib.sh`
- Modify: `deploy/backup/backup.sh`, `restore.sh`, `verify.sh`, `drift.sh` —
  wherever each one reaches the database. Read each before editing; they do not
  all touch it, and the grep in Step 3 is what decides, not this list.

**Interfaces:**
- Produces: a `DB_COMPOSE` array in each script pointing at the platform's
  compose file, used for every `exec db`, while `COMPOSE` keeps pointing at this
  repository's own file for `up`, `ps` and `run app`.

- [ ] **Step 1: Add the second compose target**

In all three scripts, beside the existing `COMPOSE=(...)`:

```bash
# PostgreSQL belongs to the platform's compose project (cg1618-apps/platform),
# so a dump reaches it through that file rather than this one. Two variables,
# not one: `up`, `ps` and `run app` still mean this repository's project.
PLATFORM_DIR="${PLATFORM_DIR:-${HOME}/cg1618}"
DB_COMPOSE=(docker compose -f "${PLATFORM_DIR}/docker-compose.prod.yml")
```

- [ ] **Step 2: Repoint every database call**

In `deploy/deploy.sh`, the dump, the `alembic_version` read; in
`deploy/backup/lib.sh`'s consumers (`backup.sh`'s stamp and dump,
`restore.sh`, `verify.sh`, `drift.sh` where they touch the database):

```bash
"${DB_COMPOSE[@]}" exec -T db pg_dump -U "${POSTGRES_USER}" -Fc -d "${POSTGRES_DB}"
"${DB_COMPOSE[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" ...
```

Leave `"${COMPOSE[@]}" run --rm --no-deps --entrypoint alembic app ...` in
`rollback.sh` alone — that runs the *app* image and belongs to this project.
`--no-deps` is now redundant rather than wrong, and its comment should say so.

- [ ] **Step 3: Grep for anything missed**

```bash
cd /c/Users/cgent/Documents/cg1618/media
grep -rn 'COMPOSE\[@\]}" exec' deploy/
```

Every remaining hit must be `DB_COMPOSE`. A `COMPOSE ... exec db` left behind
fails with "no such service: db" the first time it runs, which for
`backup.sh` means at 03:00 unattended.

- [ ] **Step 4: shellcheck and commit**

```bash
shellcheck deploy/*.sh deploy/backup/*.sh
git add deploy/deploy.sh deploy/rollback.sh deploy/backup/lib.sh deploy/backup/backup.sh deploy/backup/restore.sh deploy/backup/verify.sh deploy/backup/drift.sh
git commit -m "fix: reach PostgreSQL through the platform's compose project"
```

---

### Task 6: Open both pull requests

**Interfaces:**
- Produces: one pull request per repository, both green, neither merged until
  the cutover is about to happen.

- [ ] **Step 1: Push both branches and show the owner both bodies**

Opening and merging are the owner's. Say plainly in both bodies that the pair
must land close together and that `media.cg1618.com` is down during the cutover.

- [ ] **Step 2: Merge platform first, then media — and do not release either to `main` yet**

`main` is what the box deploys from. Merging to `dev` is safe; the release is
Task 7's first move, done with someone watching.

---

### Task 7: The cutover

**This is the window.** Everything above changed nothing on the box.

- [ ] **Step 1: Confirm the way back is still true**

```bash
ssh homelab
cat ~/pre_split_state.txt
docker volume ls --format '{{.Name}}' | grep pgdata      # media_pgdata present
```

- [ ] **Step 2: Take the final dump**

```bash
cd ~/anime_site && ./deploy/backup/backup.sh
cp ~/backups/$(ls -t ~/backups | grep -m1 '\.dump$') ~/pre_split_final.dump
ls -l ~/pre_split_final.dump
```

- [ ] **Step 3: Clone the platform repository onto the box**

```bash
cd ~ && git clone --branch main https://github.com/cg1618-apps/platform.git cg1618
```

Then create `~/cg1618/.env` from `.env.example` by hand, taking
`POSTGRES_PASSWORD`, `TUNNEL_ID` and `CLOUDFLARED_CREDENTIALS` from
`~/anime_site/.env`. **Do not print either file.** Confirm it loaded by
behaviour instead:

```bash
cd ~/cg1618 && docker compose -f docker-compose.prod.yml config >/dev/null && echo "env resolves"
```

- [ ] **Step 4: Stop the old stack**

The site is down from here until Step 8.

```bash
cd ~/anime_site && docker compose -f docker-compose.prod.yml down
docker ps            # expect none of media-*
docker volume ls     # media_pgdata still there - NOT removed
```

- [ ] **Step 5: Bring up the platform stack and restore the database**

```bash
cd ~/cg1618
docker compose -f docker-compose.prod.yml up -d db
docker compose -f docker-compose.prod.yml exec -T db pg_isready -U postgres

# The app's database, created beside the maintenance one.
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U postgres -c "CREATE DATABASE anime_site_db"
docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U postgres -d anime_site_db --no-owner < ~/pre_split_final.dump
```

- [ ] **Step 6: Verify the restored database against Task 1's numbers**

```bash
cd ~/cg1618
now="$(docker compose -f docker-compose.prod.yml exec -T db \
  psql -U postgres -d anime_site_db -tAc \
  "SELECT 'anime=' || (SELECT count(*) FROM anime)
        || ' media=' || (SELECT count(*) FROM media)
        || ' users=' || (SELECT count(*) FROM users)
        || ' rev='   || (SELECT version_num FROM alembic_version)")"
before="$(grep -o 'anime=.*' ~/pre_split_state.txt)"
echo "before: ${before}"
echo "now:    ${now}"
[ "${before}" = "${now}" ] && echo "IDENTICAL" || echo "DIFFERENT - stop and roll back"
```

**If the counts differ, stop and roll back** (Task 1 Step 3). A restored
database that is short a table is the one failure this step exists to catch,
and it is invisible once the app is up and serving most pages.

- [ ] **Step 7: Deploy the media app onto the new network**

Release both `dev` branches to `main` now — platform first — and let the box's
own Deploy workflow pull the media half. It runs `deploy.sh --ci`, which dumps
(now through `DB_COMPOSE`), pulls, rebuilds and waits on health.

```bash
cd ~/cg1618 && docker compose -f docker-compose.prod.yml up -d      # + cloudflared
gh run watch <the Deploy run> -R cg1618-apps/media --exit-status
```

- [ ] **Step 8: Verify the whole path**

```bash
ssh homelab
cd ~/anime_site && ./deploy/health.sh 180                       # app answers internally
docker network inspect cg1618 --format '{{range .Containers}}{{.Name}} {{end}}'
curl -sI https://media.cg1618.com | head -1                      # through the tunnel
```

Expected: `healthy`, both `cg1618-db-1` and `media-app-1` on the network, and
`HTTP/2 200`. Then open the site and load one entry detail page — covers and
uploaded images come from bind mounts that this step never touched, so a missing
image means the mount moved, not the data.

- [ ] **Step 9: Leave the old volume alone**

`media_pgdata` stays until a week of normal operation has passed, including at
least one nightly backup and one verify drill. Removing it is a one-line change
nobody is forced to make today:

```bash
docker volume rm media_pgdata          # NOT today
```

---

### Task 8: Repoint the backup units and prove they still run

The timers call `~/anime_site/deploy/backup/*.sh`, which still exist and are
still the media tracker's — only their database access moved, in Task 5. What
has to be proven is that they still work from systemd's environment, not just
from an interactive shell.

- [ ] **Step 1: Run each job by hand first**

```bash
ssh homelab
cd ~/anime_site
./deploy/backup/backup.sh
./deploy/backup/verify.sh
./deploy/backup/drift.sh
```

- [ ] **Step 2: Then through systemd, which is the one that counts**

```bash
sudo systemctl start media-backup.service
journalctl -u media-backup.service -n 30 --no-pager
systemctl list-timers 'media-*' --no-pager
```

`PLATFORM_DIR` defaults to `${HOME}/cg1618`, and `HOME` under a systemd
`User=cgentle1618` unit is that user's — but confirm it in the journal rather
than assuming, because a wrong `HOME` here fails at 03:00 with nobody watching.

- [ ] **Step 3: Confirm Healthchecks saw it**

The run must move its check, not merely exit 0 locally. A ping that reports to
nowhere is the failure `hc_ping` was written to make loud.

---

### Task 9: Documentation

- [ ] **Step 1: `docs/deployment-selfhost.md` in the media repository**

It describes three containers in one stack. It now describes one, and says
where the other two live. Bump `Last verified`.

- [ ] **Step 2: A platform page for the shared stack**

What `docker-compose.prod.yml` here runs, the `cg1618` network and the `db`
alias contract, how an app joins, and that the ingress is generated.

- [ ] **Step 3: `docs/notes/decisions.md` in the media repository**

One bullet: the split happened, the database moved by dump and restore into
`cg1618_pgdata` rather than reusing `media_pgdata`, the app's configuration did
not change because PostgreSQL kept the alias `db`, and `depends_on` was traded
for `restart: unless-stopped` because compose cannot order across projects.

---

## What this step deliberately does not do

- **No per-app role.** The media app still connects as the superuser. The
  spec's "one database and one role per app" arrives with `bin/provision` in
  step 4, where the role can be created and granted in one place.
- **No `bin/deploy`, no reusable workflow.** Step 4. This step edits the
  existing scripts as little as it can, precisely because they are about to be
  replaced.
- **`deploy/backup/` does not move to this repository**, though the spec's
  "what moves" table puts it here. Its scripts stamp the media database with the
  *media* repository's git revision and report to media's own Healthchecks
  checks, so moving them before they are parameterised per app would mean
  hard-coding one app into the platform. They move in step 4, with `bin/deploy`.
  What changes here is only where they reach PostgreSQL.
- **The box's checkout stays at `~/anime_site`.** `deploy.yml`, the systemd
  units and the bind mounts all name it; renaming belongs with the pipeline
  rewrite.
- **The apex page does not arrive.** It is step 6, and it needs a port on the
  network this step creates rather than the other way round.

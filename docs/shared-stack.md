# The shared stack

Last verified: 2026-09-18

`docker-compose.prod.yml` in this repository runs the half of the box that
belongs to no single application: one PostgreSQL and one Cloudflare Tunnel. It
is checked out at `~/cg1618` on the box and started from there.

```bash
cd ~/cg1618
docker compose -f docker-compose.prod.yml up -d
```

Each application runs its own compose project holding only its own service, and
joins the network declared here.

## The contract an application joins on

| | |
|---|---|
| Network | `cg1618`, declared here, joined by an app as `external: true` |
| Database host | `db` (also `postgres`) — network aliases on the PostgreSQL service |
| App's own alias | `<name>-app`, which is what the generated ingress routes to |
| Port | whatever `apps.yml` assigns the app; nothing is published to the host |

**The alias `db` is not cosmetic.** It is the hostname the media tracker's
connection string already used when its database lived in its own compose
project, so keeping it meant that moving the database changed no application
configuration at all — and the box's `.env`, which cannot travel and cannot be
reconstructed, was never edited during the cutover.

**`<name>-app` is a two-sided contract.** The app sets it as a network alias;
`bin/generate_ingress.py` writes `http://<name>-app:<port>` into the tunnel's
rules from `apps.yml`. Change one side alone and the hostname returns 502 while
both files still read correctly on their own. `tests/unit/test_prod_compose.py`
in the media repository pins its half.

## What an app cannot rely on

**Ordering.** Compose cannot express `depends_on` across projects, so an
application must tolerate PostgreSQL not being up yet. `restart:
unless-stopped` is the mechanism: the container exits, docker restarts it, and
it succeeds once the database answers. Bring this project up before the apps
and it never arises; after a power cut it costs a few restarts in a log.

**Its own project name.** Sourcing an app's `.env` with `set -a` exports
`COMPOSE_PROJECT_NAME`, and an exported variable beats the `.env` beside a
compose file. Any script that reads an app's `.env` and then talks to this
project must clear it:

```bash
DB_COMPOSE=(env -u COMPOSE_PROJECT_NAME docker compose -f "${PLATFORM_DIR}/docker-compose.prod.yml")
```

Without it, compose looks for `db` in the *app's* project and reports "service
db is not running" while PostgreSQL runs one container away.

## The database

One container, one database per application, in the named volume
`cg1618_pgdata`. The volume is the platform's rather than any app's, which is
why the media tracker's data was moved into it by dump and restore rather than
by pointing this project at the old `media_pgdata`: compose prefixes a volume
name with its project, and a volume named after one application holding every
application's data is a lie that outlives whoever shrugged at it.

Nothing publishes a port. To reach PostgreSQL from a laptop, forward it:

```bash
ssh -L 5433:localhost:5432 homelab    # then psql -h localhost -p 5433
```

## The tunnel

`cloudflared/config.yml` is **generated** from `apps.yml` — see
[registry.md](registry.md). The tunnel's id is not in it; it is passed on the
command line from `TUNNEL_ID`, which keeps the file static and committable. The
credentials JSON is the secret, mounted read-only from the path
`CLOUDFLARED_CREDENTIALS` names.

The tunnel has no `depends_on` on any application either. It answers 502 for a
hostname whose service is not up and recovers on its own when it is, which is
the correct behaviour for one tunnel serving several apps with independent
deploy cadences.

## The apex page

`cg1618.com` is served by a third container in this project: `nginx:alpine`
listening on **8007**, with `apex/index.html` and `apex/nginx.conf` mounted
read-only. The page is generated from `apps.yml` and committed; the container
runs no application code and has no database.

Its health probe is `/healthz` rather than `/`, because `try_files` serves the
page for any path — a probe against `/` cannot tell a working server from one
serving a stale document.

## What is not here yet

Deploying is still each application's own `deploy/` directory. The reusable
workflow, `bin/deploy` and `bin/provision` — which is what creates an app's
database and role — arrive with the next step of the platform sequence. Until
then an application's deploy script reaches this project directly, and the
media tracker's `DB_COMPOSE` is the pattern.

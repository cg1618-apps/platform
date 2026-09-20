# The shared stack

Last verified: 2026-09-19

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
listening on **8007**, with `apex/html/` and `apex/conf/` mounted
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

## Every service caps its log driver

Docker's default `json-file` driver has **no size limit at all**. Nothing
rotates it and nothing prunes it, so a container's log grows until the disk is
full — and on this box that is the shared PostgreSQL and every hostname going
down together, from a cause that will have been accumulating for months. It is
the slowest failure here and so the one least likely to be attributed
correctly.

Every service in `docker-compose.prod.yml` therefore takes the `log_rotation`
anchor:

```yaml
x-logging: &log_rotation
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
```

Both values are quoted. `max-file` as a YAML integer is rejected when the
container starts, which is a failure that reaches the box rather than CI.

`tests/test_deploy.py` asserts that every service declares it, so a service
added later cannot inherit the unbounded default by omission.

The cap is the docker half. What an app puts *into* the stream — JSON lines,
the field names, the request id — is [logging.md](logging.md).

**This covers this compose file only, and each app's covers its own.** What is
covered by neither is anything started outside a compose file — a one-off
`docker run`, the Actions runner, whatever a later session starts by hand.
Those take the daemon default, and **the box has no `/etc/docker/daemon.json`
at all**, so the default there is still the uncapped one. Setting it is a root
change on the box rather than anything this repository can make true:

```bash
# on the box, once
sudo tee /etc/docker/daemon.json <<'EOF'
{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "5"}}
EOF
sudo systemctl restart docker
```

That restart bounces every container, so it is done deliberately rather than
folded into something else. It is outstanding; see `docs/open-items.md`. Note
that it would not make the per-service blocks redundant even once done — the
daemon default is not in this repository, where a diff would show it changing,
and a service relying on it alone is one nobody decided about.

**This bounds a buffer; it is not a retention policy.** 10 MB × 5 files is
months of history at the rate the box currently produces — roughly 7 KB per
hour per app container, about 1 MB a day across all seven — but a
`docker compose up -d` that recreates a container discards that container's
log outright, whatever its size. So the cap is protection against the disk
filling, and nothing here is a place to look something up after a deploy.

## Bind mounts are directories, never single files

Every bind mount in `docker-compose.prod.yml` names a directory. A single-file
mount pins the inode, and `git pull` replaces a file rather than writing
through it — so the container goes on serving the old content while the file
on disk is correct, and neither side says anything is wrong. The apex page was
mounted that way the day travel went live: the file on disk linked to travel
and the page being served still said "planned", and `SIGHUP` to cloudflared
reloaded a config that had been replaced underneath it. A directory mount
re-resolves the name on every open.

`tests/test_deploy.py` asserts it, so a file mount cannot come back.

The one exception is the tunnel credentials, which are mounted from outside
the repository by absolute path. Nothing rewrites that file, so the inode
problem does not apply to it.

**And never nested.** A mount whose destination contains another mount's
destination makes docker create the inner mountpoint inside the outer mount,
which fails outright when the outer one is read-only — the container exits
with `read-only file system`. That took the tunnel, and so every hostname on
the box, down for a minute and a half. The tunnel's config directory is
therefore mounted at `/etc/cloudflared/conf` rather than `/etc/cloudflared`,
so it is a sibling of the credentials file rather than its parent. Making the
mountpoint exist is not an alternative: that file is a credential and is never
committed.

`tests/test_deploy.py` asserts this too.

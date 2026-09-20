# Logging

Last verified: 2026-09-20

The contract every application's logging satisfies, and the one place the
result is read. Like the app contract in [registry.md](registry.md), this is a
**requirement on apps** rather than a description of what all four do today —
the conformance table at the bottom says where each one actually is, and it is
the honest part of this page.

Nothing here is about audit trails. "Who changed this entry", "Pull All
rewrote 312 rows" — that is domain data, it belongs in the app's own
PostgreSQL and its own UI, and it is not logging. The distinction is worth
holding onto: one of these is read by a person asking a question about their
data, the other by whoever is working out why the box is behaving strangely.
See [notes/decisions.md](notes/decisions.md), "Apps emit streams; the box
aggregates".

## The stream

**Every app writes to stdout and stderr, and nowhere else.** No app opens a
log file, rotates one, or writes a log line to its database.

This is not a preference. A container's stdout is what the daemon captures and
what any collector can read; a file inside a container is invisible from
outside it, disappears when the container is recreated, and needs its own
rotation that nobody will configure. An app that logs to its database couples
its diagnostics to the thing most likely to be broken when it needs them.

## Two formats, chosen by environment

**Production is JSON lines** — one JSON object per line, no pretty-printing,
no multi-line records.

| Field | | |
| --- | --- | --- |
| `timestamp` | always | ISO 8601, **UTC**, millisecond precision, explicit offset: `2026-09-20T13:48:53.214+00:00` |
| `level` | always | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `logger` | always | the logger name, e.g. `app.routers.entries` |
| `message` | always | the formatted message |
| `app` | always | the registry name — `media`, `food`, `travel`, `art` |
| `request_id` | inside a request | see below |
| `exc_info` | on an exception | the formatted traceback, as one string |

An app may add fields — `media` adds `stack_info`. It may not rename or drop
these.

**`request_id` is omitted outside a request, not written as `null`.** Every
startup line, every migration and every background task would otherwise carry
a null field into the collector's index for nothing. This is a contract-level
choice rather than each app's, because it decides what a query can assume:
`request_id` present means "this happened inside a request", and that is only
true if nobody writes the key when it does not apply.

`exc_info` and `stack_info` are named after `logging`'s own keyword arguments
rather than invented as `traceback` and `stack`, so a reader who knows Python
already knows what they hold and where they came from.

`+00:00` rather than `Z` because that is what `datetime.isoformat()` produces
and there is no reason to post-process it. They denote the same instant and a
reader of the aggregated stream should not have to notice which an app chose,
so the contract picks one rather than allowing both.

`app` is redundant with the container label the collector already attaches,
and it is required anyway: a line pasted into a terminal, a bug report or a
message to another session arrives with no label on it, and "which app was
this" is the first question about an orphaned line.

**Development is the plain human format**, because nobody greps their own
terminal with `jq`:

```
%(asctime)s %(levelname)-8s %(name)s: %(message)s
```

**The choice is made by `APP_ENV` / `settings.is_development`, not by a
separate switch.** A second flag is a second thing to get wrong, and the way
it gets wrong is that production quietly emits the development format for
months while every line still looks fine to a human reading `docker logs`.

## uvicorn's loggers have to be taken over explicitly

**This is the part that will be got wrong.** uvicorn installs its own
handlers and formatters on `uvicorn`, `uvicorn.access` and `uvicorn.error` at
startup, and sets `propagate = False` on them. A `dictConfig` that configures
only the root logger therefore does not touch them: the app's own lines become
JSON and **every request line stays plain text**.

The result is a stream that is half structured, in which the half that does
not parse is the access log — the highest-volume and most useful part of it.
It looks completely fine in `docker logs`, which is the only place anyone
checks before shipping.

So an app's `dictConfig` must name all three loggers, point them at the same
handler, and set `propagate: False` on each:

```python
"loggers": {
    "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
    "uvicorn.access": {"handlers": ["console"], "level": level, "propagate": False},
    "uvicorn.error": {"handlers": ["console"], "level": level, "propagate": False},
},
```

`propagate: False` is load-bearing in the other direction too. Attaching the
console handler *and* leaving propagation on gives every uvicorn line twice —
once from its own handler and once from root's.

An app on something other than uvicorn has the same obligation about whatever
its server logs through. The rule is that **one process emits one format**.

**Land the JSON formatter and the uvicorn takeover in the same commit.** They
are two edits to one file and it is tempting to do them in sequence. The window
between them is precisely the mixed stream described above — and it is
invisible in `docker logs`, so a commit that opens it looks like a commit that
worked. `food` is the app this is waiting to happen to: it is plain text
everywhere today, which is consistent and fine, and it becomes a mixed stream
the moment it gains a JSON formatter without the takeover.

## `%s` arguments, never f-strings

```python
logger.info("pulled %s entries for %s", count, username)   # yes
logger.info(f"pulled {count} entries for {username}")      # no
```

This is in the contract rather than in four style guides because the reason is
mechanical rather than taste. An f-string renders at the call site, so by the
time `logging` sees the record there is one opaque string: `record.msg` holds
the finished sentence and `record.args` is empty.

What that costs:

- **The template stops being a grouping key.** With `%s`, ten thousand requests
  share one `record.msg`, so the collector can count and group them as one kind
  of event. With an f-string every line is a distinct string and there is
  nothing to group by but substring matching.
- **The arguments cannot ever become fields.** No app emits them as fields
  today — every formatter here calls `record.getMessage()`, which renders the
  same result either way — but `%s` leaves `record.args` populated, so that is
  a formatter change later rather than a rewrite of every call site. With
  f-strings the information is destroyed at the call site and no later change
  can recover it.
- **Formatting happens only if the line is emitted**, so a `DEBUG` call in a
  hot path costs nothing at `INFO`.

`media` converted 85 call sites and asserts it with an AST scan over `app/`,
with a mirror test proving the detector fires on a known-bad module — a scan
that finds nothing passes whether or not it works.

## Request IDs

With four apps behind one tunnel, a request id is the difference between a
searchable log and a pile of lines.

1. **Read `X-Request-ID` from the inbound request.**
2. **Accept it only if it matches `^[A-Za-z0-9_-]{1,64}$`.** Otherwise ignore
   what was sent and generate a fresh `uuid4().hex`.
3. **Put it on every line logged during that request**, as `request_id`.
4. **Echo it back on the response as `X-Request-ID`** — whichever value was
   actually used, not the one that arrived.

**Step 2 is not optional, and the reason is specific to this box.** `media`
and `food` are `exposure: public`, and cloudflared forwards client headers to
the origin unmodified, so on those two hostnames this header is attacker-
controlled from the open internet. JSON encoding does prevent the classic
log-forging attack — a newline in the value is escaped, not written — so this
is not a hole through which fake log lines can be injected. What it is:

- an unbounded value rides on **every line** of that request, so a one-megabyte
  request id is a one-megabyte tax per line, straight into the collector's
  storage;
- a client can deliberately reuse another request's id and make correlation
  lie, which is worse than having no correlation, because the log looks
  coherent.

Validating costs one regex and removes both.

Cloudflare's own `CF-Ray` is also present and is a genuine per-request id from
the edge. It is not used as the value because it does not exist when the app
is reached any other way — from another container on the `cg1618` network, from
a health probe, or in development — and an id that is present only on the
happy path is one nobody can rely on.

## The docker side

Every service, platform and app, caps its log driver: `json-file`,
`max-size: "10m"`, `max-file: "5"`. The platform's half and what it does *not*
cover are in [shared-stack.md](shared-stack.md); all four apps now declare the
same block in their own `docker-compose.prod.yml`, and `food`, `travel` and
`art` assert it in their `test_prod_compose.py` alongside the other compose
invariants.

That cap bounds a buffer. It is not where logs are read from and it is not
retention — recreating a container discards its log entirely, which happens on
every deploy.

## Where this is read

**Defined and CI-verified; not serving yet.** `docker-compose.prod.yml` in
this repository runs Loki, Alloy and Grafana, and every pull request starts
them, pushes real container output through them and asserts Loki can answer a
query about it. What has not happened is the last step:
`logs.cg1618.com` is `status: planned` in `apps.yml`, so the tunnel routes
nothing to it.

Until it is live, production output is `docker logs` over SSH, per container,
from the manager session — and nothing survives a deploy. The stack itself runs
on a development machine today and is worth exploring there first; see
[Viewing it locally](#viewing-it-locally) below.

Three things stand between here and live, and each is the owner's:

1. **A Cloudflare Access application covering `logs.cg1618.com`**, and its DNS
   record. Dashboard work, and the only step that makes the gate real.
2. **`GRAFANA_ADMIN_PASSWORD` in the box's platform `.env`.** The compose entry
   uses `:?`, so the stack refuses to start without it rather than falling back
   to `admin`/`admin`.
3. **Then `status: live`**, one line, after `bin/check-exposure logs` has been
   run and has said the hostname is gated. In that order — `live` first would
   publish an unauthenticated Grafana holding four applications' logs, which is
   the `art` failure with worse contents.

The box has the headroom, measured on 2026-09-20 rather than estimated: 14.0 GB
of 15.2 GB RAM available, 80 GB of 98 GB disk free, all seven containers then
running under 550 MB together. The three new ones are expected around
400–500 MB.

Once it is live, the search that answers most questions is the request id from
[Request IDs](#request-ids) above:

```logql
{compose_project=~".+"} | json | request_id = "<the id>"
```

The label set, read back from a running Loki rather than from the Alloy config:

```
compose_project  compose_service  container  job  service_name
```

`container`, `compose_project` and `compose_service` are the ones
`observability/alloy/config.alloy` attaches, and `job` is `"docker"`.
**`service_name` is added by Loki itself**, not by Alloy — Loki 3 derives it
from the stream's labels when none is supplied, so it appears in a label query
and in nothing this repository wrote. Worth knowing before somebody goes
looking for where it is set.

**The `app` field and the `container` label are supposed to disagree, and
neither is wrong.** `media` emits `app="media"` — the registry name, per [Two
formats](#two-formats-chosen-by-environment) — while its container is
`media-app-1` and the label derived from it says so. One is what the
application calls itself, the other is what docker calls the process; they
differ by the `-app-1` suffix and by nothing else.

That is worth a sentence because the obvious tidying is wrong in both
directions. Deriving `app` from the container name would make it empty for
anything not in a container. Relabelling the container to match would break
the `<name>-app` network alias the generated ingress routes to, and the
hostname would answer 502 while both files still read correctly on their own.
Query by the label; read `app` off a line that arrived without one.

## Viewing it locally

```powershell
.\dev-logs.ps1              # start, wait for both, open Grafana
.\dev-logs.ps1 -Down        # stop; local history is kept
.\dev-logs.ps1 -Clean       # stop and discard the local volumes too
```

Grafana is on **http://127.0.0.1:8008/**, `admin` / `admin`, with Loki already
provisioned as the default datasource — go to **Explore**. Loki's own API is on
`127.0.0.1:3100` if you would rather `curl` it.

`docker-compose.dev-logs.yml` runs Loki, Alloy and Grafana and **nothing else**.
It is a separate file rather than a profile on the production one because two of
those other services must never start on a laptop:

- **`cloudflared` would connect a second tunnel with the box's credentials.**
  Cloudflare load-balances a tunnel's connections across its replicas, so a
  share of real production traffic would begin arriving at the laptop and be
  answered by whatever it happened to be serving. Nothing announces it; both
  containers look healthy.
- **`db` would bind 5432** against `anime_site_postgres_db`, which every app's
  `dev.ps1` starts and every app's tests use.

`tests/test_dev_logs.py` asserts both absences, that the project name is pinned
to `cg1618-dev-logs` so a `docker compose -f docker-compose.prod.yml down` in
this directory cannot delete the local stack, that nothing is published beyond
loopback, and that the Loki, Alloy and Grafana configs mounted are **the same
files the box runs** rather than a second copy that would drift.

### What it will not show you, and why

**Your four applications are not in it.** Alloy discovers containers through the
docker socket, and in development the apps run as uvicorn processes started by
`dev.ps1` — not containers. There is nothing of theirs for Alloy to tail.

**And there would be nothing structured to look at if there were.** The contract
above selects the plain human format whenever `is_development` is true, which is
the right call: a terminal is better at reading a sentence than Grafana is, and
`jq` on your own dev output is a chore nobody should have. Structured logging
earns its keep in production, across four apps, behind one tunnel.

So locally you get every *container* on the machine — the shared PostgreSQL,
and the collector's own three, which is enough to learn LogQL and confirm the
stack works end to end.

### If you do want real application lines locally

Run one app the way production runs it, in its own container, which makes it
visible to Alloy and puts it in production format:

```powershell
cd food
docker compose -f docker-compose.prod.yml up -d --build
```

That needs the app's `.env` and the `cg1618` network, and it is a rehearsal of
the deploy rather than a way to develop. It is worth doing once, before the
collector goes live on the box, to see what the real stream looks like.

### Reading production

Not yet possible. `logs.cg1618.com` is `status: planned`, so the tunnel routes
nothing to it, and the three steps that change that are in
[open-items.md](open-items.md). Until then production output is `docker logs`
over SSH, per container, and nothing survives a deploy.

## Who conforms today

This is the part to keep accurate; it is the only reason a contract page is not
just a wish.

| App | `logging_config.py` | JSON in production | uvicorn taken over | request id | log driver capped |
| --- | --- | --- | --- | --- | --- |
| `media` | yes | yes | yes | yes | yes |
| `food` | yes | yes | yes | yes | yes |
| `travel` | yes | yes | yes | yes | yes |
| `art` | yes | yes | yes | yes | yes |

**All four, on each app's `dev`.** None of it is on any app's `main`, so
nothing is emitting this in production yet — and the collector is not serving
either, so there is currently nowhere for it to go. Both of those are release
decisions rather than gaps in the contract.

### The order they arrived in, which is not the usual one

`food` wrote the first `logging_config.py` — a `dictConfig` called once from
`main.py`, `disable_existing_loggers: False`, `sqlalchemy.engine` pinned to
`WARNING` — while `media` had no such file at all: its root log level was set by
a `logging.basicConfig` running as an import side effect of one router, so what
got logged depended on which module was imported first.

`media` is the reference by default under "House style", and on this one thing
it was the app that was wrong. See [notes/decisions.md](notes/decisions.md),
"`media` is the reference because it is read, not because it is right". `media`
then built the fullest implementation on top of food's shape, so an app
starting from zero should read `food` for the minimal correct `dictConfig` and
`media` for the formatters, the request-id filter and the uvicorn takeover.

### Why `travel` and `art` adopted it with nothing to log

Both had zero log calls when this landed, which is the argument for doing it
then rather than against. `media` converted **85 f-string call sites** when the
contract arrived after the code, and that conversion was the bulk of its work.
The AST guard that forbids f-strings costs nothing to add to an app with no log
calls and costs 85 call sites to add later; the middleware is likewise cheaper
to put under a request path before it carries traffic.

The one thing that genuinely differs between them is the reason the inbound
`X-Request-ID` is validated. `media` and `food` are `public`, so the header
arrives from the open internet. `travel` and `art` are `cloudflare-access`, so
it cannot — and they validate it identically anyway, because the collector
indexes every app together and because `exposure` is one line in `apps.yml`
that `docs/registry.md` says both are expected to change one day. A validator
that was only correct while an app was private is one nobody adds on the day it
goes public.

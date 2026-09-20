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
cover are in [shared-stack.md](shared-stack.md); an app declares the same
block in its own `docker-compose.prod.yml`.

That cap bounds a buffer. It is not where logs are read from and it is not
retention — recreating a container discards its log entirely, which happens on
every deploy.

## Where this is read

**Not built yet.** Today the only way to read production output is
`docker logs` over SSH, on the box, per container — which means the manager
session, and means nothing survives a deploy.

The plan is one collector on the box for all of it: Grafana Alloy tailing the
docker socket and labelling streams by container, Loki storing them, Grafana
reading them, behind a `cloudflare-access` hostname in `apps.yml` like
anything else. The box has the headroom — measured 2026-09-20: 14.0 GB of
15.2 GB RAM available, 80 GB of 98 GB disk free, all seven current containers
together under 550 MB. This page gets its "where to look" section when that
lands, and not before.

## Who conforms today

This is the part to keep accurate; it is the only reason a contract page is
not just a wish.

| App | `logging_config.py` | JSON in production | uvicorn taken over | request id |
| --- | --- | --- | --- | --- |
| `media` | **yes** | **yes** | **yes** | **yes** |
| `food` | **yes** | no | no | no |
| `travel` | no | no | no | no |
| `art` | no | no | no | no |

**`food` is the origin of this shape and `media` is now the fullest example
of it**, which is an ordering worth stating because it is the reverse of the
usual one. `food/app/logging_config.py` came first: a `dictConfig` called once
from `main.py`, `disable_existing_loggers: False`, `sqlalchemy.engine` pinned
to `WARNING`. Until `feat/structured-logging`, `media` had no such file at all
— its root log level was set by a `logging.basicConfig` running as an import
side effect of one router, so what got logged depended on which module was
imported first. `media` is the reference by default under "House style", and
on this one thing it was the app that was wrong; see
[notes/decisions.md](notes/decisions.md), "`media` is the reference because it
is read, not because it is right".

So an app starting from zero should read both: `food` for the minimal correct
`dictConfig`, `media` for the JSON formatter, the request-id filter and the
uvicorn takeover on top of it.

`media`'s row is what is on `feat/structured-logging` in that checkout, read
rather than reported — `app/logging_config.py` and `app/request_context.py`.
It is not on `main`, so nothing is emitting this in production yet.

What `food` does not yet have is the JSON formatter, the uvicorn takeover and
the request-id middleware; its `logging_config.py` predates this contract and
satisfies the half of it that existed then. **`travel` and `art` have nothing
at all** — no `logging_config.py`, no `dictConfig`, no request id. Their root
log level is whatever `logging` defaults to under whatever imported first.

Nobody is assigned to those three. One app conforming to a contract four apps
are supposed to share is the state this table exists to make visible rather
than comfortable.

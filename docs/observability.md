# Observability: the collector and the dashboard

Last verified: 2026-09-20

What the box does with the lines its containers emit, and how to read the
result. The *contract* the applications emit against — field names, formats,
request-id rules — is [logging.md](logging.md). This page is the other half,
and the reader it has in mind is someone trying to find out what went wrong.

**Where it is.** `logs.cg1618.com`, Cloudflare Access in front, Grafana behind
it, Loki underneath, and Grafana Alloy tailing every container on the box
through the docker socket. All of it runs from the platform's
`docker-compose.prod.yml`; the pieces and their trade-offs — why Loki rather
than Elasticsearch, why Alloy holds the docker socket, why Loki has no
healthcheck — are in [shared-stack.md](shared-stack.md).

**It survives deploys.** That is the difference from `docker logs`, which is
discarded whenever a container is recreated.

## The dashboard

**Dashboards → cg1618 → Box overview.** It exists so the recurring questions
are already asked; Explore is for the ones that are not.

It is **provisioned from files** — `observability/grafana/dashboards/` in this
repository — so it survives a rebuild and appears in a pull request diff.
`allowUiUpdates: false`, which means it is read-only in the browser: changing
it means editing the JSON and landing it. Every panel carries a description;
hover the ⓘ rather than guessing what a panel counts.

### The four standing questions

| Question | Panel | A bad answer looks like |
| --- | --- | --- |
| How much is happening? | Lines, selected range · Log volume by container | a step change with no deploy behind it |
| How much of it is wrong? | Application errors · by app | any number above zero |
| Is everything still alive? | **Containers reporting** | a number below ten |
| What happened to this request? | Find one request | — |

### `Containers reporting` is the alarm; everything else is context

The box runs **ten** containers: four apps, `db`, `cloudflared`, `apex`, and
the collector's own three. So ten is right and anything less is wrong, with no
interpretation required. A container that stops logging has almost always
stopped.

Nothing else on the dashboard is that unambiguous. Learn this one first.

### `Lines, selected range` is a change detector, not a measurement

A reading of 5,369 over six hours is weather. What matters is a **step change
with no deploy behind it** — doubling usually means something is retrying in a
loop, halving usually means something stopped serving.

The same applies to **Log volume by container**. The quieter apps normally sit
at nearly identical counts, because that is the health probe and almost nothing
else; measured on 2026-09-20, `art` 717, `travel` 717, `media` 687, `food` 740.
**One app diverging from its neighbours is the signal**, more than any absolute
number. A container going quiet matters as much as one going loud.

Grafana dominates the chart — 2,392 lines in the same window — because it is
watching Loki. That is normal and is not worth investigating.

### `Application errors` reads a field, and the reason matters

```logql
{container=~".+-app-1"} | json | level=~"ERROR|CRITICAL"
```

Not a text search. The distinction is not pedantry — this panel *was* a text
match, and it was wrong by a wide margin.

**Measured on 2026-09-20.** The text version reported **49** errors across the
box. Of those, **40 were Grafana describing itself** in lines that happen to
contain the word, and **4 were `food`'s startup lines**:

```json
{"level": "INFO", "logger": "uvicorn.error", "message": "Application startup complete.", "app": "food"}
```

An `INFO` record saying startup succeeded, matched because uvicorn's
general-purpose logger is *named* `uvicorn.error` — it is not an error logger.
The same window, queried on the field, returned **zero**. Four versus nought on
one container, forty-nine versus nought across the box.

So the panel counts what the application *said its level was*, and it covers
the four apps only, because only they emit JSON.

**Grouped by `app`, not `container`.** `app` is what the application calls
itself — the registry name — and `container` is what docker calls the process.
They differ by the `-app-1` suffix and neither is wrong; see
[logging.md](logging.md).

### `Infrastructure lines matching 'error'` is deliberately the noisy one

`db`, `cloudflared`, `apex`, `loki`, `alloy`, `grafana`. These are third-party
containers that do not emit the platform's JSON, so this panel *is* a text
match and it *does* over-count.

It is kept rather than dropped for being noisy, because **a PostgreSQL or
tunnel error matters more than most application errors** and nothing else would
surface it. Read it as a place to look, never as a count.

### The three variables

`Container` drives the drill-down panel and is populated from Loki, so a new
app appears there without editing anything. `Search` is a substring filter for
that panel. `Request ID` takes a value pasted from an `X-Request-ID` response
header.

**All three are blank-safe**: an empty Loki line filter is a no-op rather than
an error, so blank means "no filter" rather than "no results". The consequence
is that *Find one request* shows everything until you paste something in. That
is not a bug.

## Finding one request

The single most useful thing here, and the reason the request-id middleware
exists. Every response carries the id:

```
x-request-id: 15b2b9775f64473eb5ed4d15b6a36451
```

Paste it into `Request ID` and you get every line that request produced, across
whichever container handled it. A line filter rather than `| json`, so it works
on the apps' JSON and the infrastructure's plain text alike.

## Queries worth knowing

LogQL builds in four layers, and only the first is mandatory.

```logql
{container="media-app-1"}                                  selector  (uses the index)
{container="media-app-1"} |= "backup"                      line filter (scans text)
{container="media-app-1"} | json | level="ERROR"           parser, then a field
sum by (app) (rate({container=~".+-app-1"} | json [5m]))   metric  (draws a graph)
```

**Narrow with labels, filter with text, parse into fields, aggregate into
numbers.** Every query is a prefix of that sentence. The selector is the only
part that touches Loki's index, so it decides how much data gets read — widen
the filters before widening the braces.

The labels Alloy attaches are `container`, `compose_project`, `compose_service`
and `job="docker"`. Loki adds `service_name` itself when a stream supplies
none; it is in no config in this repository, which is worth knowing before
going to look for where it is set.

### The three failure modes that read as bugs

| Symptom | Cause |
| --- | --- |
| "No data" on a query you know is right | the time range is Last 1 hour; widen it |
| A parsed query returns nothing sensible | `__error__="JSONParserErr"` — wrong parser for that line. Drop them with `\| __error__=""` |
| A graph panel is empty | it was given a log query, not a metric query |

`| json` against a container that does not emit JSON does not throw. Loki
attaches `__error__` to each line and carries on, which is why the symptom is
confusing rather than loud.

## Running the whole thing locally

```
dev.cmd            start Loki, Alloy and Grafana, and open it
dev.cmd -Down      stop; local history is kept
dev.cmd -Clean     stop and discard the local volumes too
```

Grafana on **http://127.0.0.1:8008/**, **no login** — the local stack runs
anonymous at the `Admin` role, so the page opens straight into Explore.
`admin` / `admin` still works if you want to sign in as a real user. The same
provisioned datasource and dashboards as the box.

`docker-compose.dev-logs.yml` runs the collector and **nothing else**. It is a
separate file rather than a profile on the production one because two of that
file's services must never start on a laptop:

- **`cloudflared` would connect a second tunnel with the box's credentials.**
  Cloudflare load-balances a tunnel's connections across its replicas, so a
  share of production traffic would arrive at the laptop and be answered by
  whatever it happened to be serving. Both containers would look healthy.
- **`db` would bind 5432** against `cg1618-dev-db`, the development database.

`tests/test_dev_logs.py` asserts both absences, that the compose project name
is pinned so a production `down` cannot delete the local stack, that nothing is
published beyond loopback, and that production carries neither anonymous-auth
key.

### What it cannot show you locally

**Your own apps.** Alloy discovers *containers*, and in development the apps
run as uvicorn processes started by `dev.ps1`. There is nothing of theirs to
tail — and nothing structured to look at if there were, because the contract
selects the plain human format whenever `is_development` is true. A terminal
reads a sentence better than Grafana does.

So locally you get every container on the machine: `cg1618-dev-db` and the
collector's own three. Enough to learn the query language, which is the point
of having it.

To see real application lines locally, run one app the way the box does:

```powershell
cd food
docker compose -f docker-compose.prod.yml up -d --build
```

That is a deploy rehearsal rather than a way to develop, and it needs the app's
`.env` and the `cg1618` network.

## The datasource uid is pinned, and that is load-bearing

`observability/grafana/datasources/loki.yml` sets `uid: loki`. Without it
Grafana generates one per instance, and a dashboard file that works on a laptop
fails on the box with "datasource not found" — which reads as a broken
dashboard rather than a broken reference.

The file also carries a `deleteDatasources` block, and it is **not** redundant.
Pinning a uid on a Grafana that already had the datasource under a generated
one makes provisioning look it up by the new uid, fail, and take the entire
provisioning module down at boot — Grafana does not start at all:

```
logger=provisioning level=error msg="Failed to provision data sources"
  error="Datasource provisioning error: data source not found"
```

Measured on the development stack, not predicted, and it would have happened
identically on the box. Deleting by name first makes the file the whole truth.
A correct boot says so:

```
provisioning.datasources msg="deleted datasource based on configuration" name=Loki
provisioning.datasources msg="inserting datasource from configuration" name=Loki uid=loki
```

## Retention

90 days, set in `observability/loki/loki-config.yml` and enforced by the
compactor. `retention_enabled: true` on the compactor is not optional: without
it `retention_period` is read, accepted, and silently does nothing.

Ninety days is chosen for how far back a question is ever asked rather than for
capacity. At the box's rate — around 1 MB a day across every container before
compression — it is well under a gigabyte.

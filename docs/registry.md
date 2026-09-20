# The application registry

Last verified: 2026-09-19

`apps.yml` at the root of this repository is the one source of truth about which
applications exist on the box and what each one is allowed to claim. The
Cloudflare Tunnel ingress, the apex page's navigation and the list of databases
the backup job dumps are all derived from it — none of them is hand-edited.

## The file

```yaml
apps:
  - name: media
    hostname: media.cg1618.com
    port: 8000
    database: media          # null is legal: an app need not have one
    repo: git@github.com:cg1618-apps/media.git   # null = the platform owns it
    exposure: public         # public | cloudflare-access | lan-only
    health_path: /api/health
    migrations: true         # does this app ship deploy/migrations?
    description: Media tracker & database
    path: "~/anime_site"     # optional; only when the checkout is not <apps dir>/<name>
```

`status` separates a **claim** from a **running service**. An entry reserves the
hostname, the port and the database name the moment an app is planned — which is
what stops a second app taking them — but only a `live` app is routed by the
tunnel and linked from the apex page. Routing a planned app would publish a
hostname that answers 502, which is worse than one that does not resolve.

`path` is **optional and almost always absent**: a checkout lives at
`<apps dir>/<name>` — `${APPS_DIR:-$HOME}/<name>` — unless it does not, and
`media` is the one that does not, because it predates the layout and sits at
`~/anime_site`. A leading `~/` means `$HOME`; anything else must be absolute,
and the schema forbids whitespace in the value.

It lives here rather than being passed in because **everything else the deploy
scripts act on is registry-derived**. It was a workflow input once, and a
caller could then name `travel` and hand it media's checkout: the database name
came from the registry and the code came from the input, so `bin/deploy` would
dump one app and deploy another. One source cannot disagree with itself.
`--app-dir` still exists on all three scripts for running them by hand against
a checkout the registry knows nothing about.

`health_path` is declared rather than assumed because the applications do not
share a stack. `/api/health` is the media tracker's answer — it opens a real
database session and compares `alembic_version` to the head the running code
expects — not a platform fact. An app written against something else exposes
something else, so the app declares it and the deploy script reads it.

`migrations` is a **declaration**, and it is the reason a lost mode bit cannot
disable the approval gate. `true` means the app ships an executable
`deploy/migrations`; `bin/deploy` and `bin/rollback` refuse when it is missing
or not executable, rather than taking silence for "this app has no schema".
`false` means the schema never changes, and a hook present anyway is refused
too — the registry and the repository disagree, and which one is right is a
person's decision rather than a script's guess. Before the key existed, an
absent hook and a hook that had lost its `+x` were the same observation, and
the second one deploys an unapproved migration with no rollback target.

Only things that **exist** are listed. An entry claims a hostname, a port and
a database; claiming them for something unbuilt is how a registry stops being
true.

Almost every entry is an application in a repository of its own. One is not —
`logs`, the box's observability, which lives in this repository and carries
`repo: null`. See "[`repo: null` — an entry the platform itself
owns](#repo-null--an-entry-the-platform-itself-owns)" below for why it is
registered while the apex page is not.

## Two layers of validation, because they catch different things

**`schema/apps.schema.json`** describes one entry: the required fields, the
`exposure` enum, a hostname inside `cg1618.com`, a port in 8000–8099, and
`additionalProperties: false` so a typo'd key fails rather than being silently
ignored by every generator downstream.

**`bin/validate_apps.py`** checks what a schema structurally cannot:

- **Uniqueness**, which is relational. No two apps may claim the same hostname,
  port or database — and a schema validates entries one at a time, so it cannot
  see a pair. `database: null` is exempt: "no database" is not a collision.
- **Which values a particular app may hold.** `journal`, `health` and `money`
  are never `public`. They hold a different class of data, and the Cloudflare
  Access decision belongs *before* an ingress rule exists rather than after it
  has been serving.

  **That list is three apps, and deliberately not five.** `travel` and `art`
  are also private today — both are `cloudflare-access` — but they are expected
  to publish something eventually: a shared trip, a finished drawing. For them,
  `public` is a change the app is meant to want, once its own visibility checks
  exist. A rule that must be deleted to allow an intended change is a speed
  bump rather than a protection, and it gets deleted in a hurry, in the same
  pull request as the feature. The three on the list are the ones where
  `public` is never correct at any point in the future, which is what makes
  refusing it meaningful.
- **That each app names its own repository**, so a copy-pasted entry cannot
  point two apps at one repo.

`migrations` needs no rule in the validator: it is per-entry and boolean, so
the schema's `required` list is the whole check. What it protects lives
elsewhere — `bin/deploy` and `bin/rollback` compare it against what is actually
on disk, and refuse when the two disagree.

Both run in CI on every pull request, and the same validator is called again
inside `bin/deploy` when that arrives. Shifting a check left is not a reason to
trust that it ran.

### Testing the refusals, not just the acceptances

`apps.yml` holds one application, so every uniqueness rule is **vacuously
satisfied** by it — a refusal test written against the real file would pass
without the rule ever firing, and would keep passing through the change that
broke it. `tests/test_validate_apps.py` therefore builds its own two-app
registries for the collision cases, and asserts the mirror case on the same
fixture for the exposure rule, so a green means the rule did the refusing rather
than something incidental.

## What is generated from it

| File | Generator | Checked by |
| --- | --- | --- |
| `cloudflared/config.yml` | `bin/generate_ingress.py` | CI, `--check` |
| `apex/html/index.html` | `bin/generate_apex.py` | CI, `--check` |

Both are committed rather than built at deploy time, so what will be served
appears in the pull request diff where a person reads it. Neither is ever
hand-edited; CI fails when the committed output and `apps.yml` disagree.

**Not everything in `apex/html/` is generated.** `favicon.svg` and
`favicon.ico` sit beside the generated page as ordinary committed assets, and
are edited by replacing the file. Only `index.html` is generator output, and
only `index.html` is what `--check` compares. The `<link rel="icon">` tags that
point at them live in `bin/generate_apex.py`'s template, because the page they
appear in is generated — so changing the icon's *filename* is a generator
change, while changing the icon's *picture* is not.

**The apex page is not in the registry.** `cg1618.com` is a rendering of
`apps.yml` rather than an application, so it has no entry and its ingress rule
is emitted unconditionally. That it is infrastructure is *not* the reason —
`logs` is infrastructure too and is registered; the reason is below. The day it needs a backend, a database,
authentication or per-user state it becomes `cg1618-apps/landing` with its own
repository, its own port and an entry like any other app — that rule is what
keeps "no application code in the infrastructure repository" honest rather than
arbitrary.

## `repo: null` — an entry the platform itself owns

Every entry above is an application in `cg1618-apps/<name>`. **`logs` is not.**
Grafana, Loki and Alloy are services in this repository's
`docker-compose.prod.yml`, so there is no repository to clone, no deploy
workflow, nothing for `bin/provision` to do and no schema to migrate. `repo:
null` says exactly that, the way `database: null` says "no database".

**Why it is in the registry at all**, when the apex page — also infrastructure,
also in this repository — deliberately is not:

`bin/check-exposure` iterates `apps.yml`. A `cloudflare-access` hostname that
is absent from this file is a hostname **nothing probes**, and a DNS record
with no Access application behind it looks identical to a working one from
everywhere except the open internet. That is precisely what happened to `art`.
An unauthenticated Grafana is worse than an unauthenticated anything else here,
because it holds every application's logs — so the argument that keeps the apex
page out (it is a rendering of the registry, it authenticates nobody, nothing
is at stake) is the argument that puts this one in.

It also reserves the port. `apex` listens on **8007** and has no entry, so
nothing stops a future app claiming 8007 and colliding with it; `logs` at 8008
cannot be taken that way.

`bin/validate_apps.py` refuses three things alongside a null `repo`, rather
than ignoring them:

| Also declared | Refused because |
| --- | --- |
| `migrations: true` | there is no `deploy/migrations` hook and nothing would ever run one |
| a `database` | `bin/provision` finds the checkout via `repo`, so it cannot provision this entry |
| a `path` | there is nothing to check out |

The `repo` **pattern** still applies when the value is present: an exemption
for null is not an exemption for a wrong name. `bin/provision` refuses such an
entry by name before it looks at anything else, because "declares no database"
would also be true and would send the reader after the wrong thing.

## Exposure, and where the gate lives

| Value | Who authenticates | When it fits |
| --- | --- | --- |
| `public` | nobody, or the app itself | anything anyone may read. The app still needs its own gate on **writes**. |
| `cloudflare-access` | Cloudflare, before the request reaches the box | one user, no accounts, nothing to log into. Zero auth code in the app. |
| `lan-only` | nothing — there is no ingress rule at all | something that should never leave the house. |

**`cloudflare-access` is all-or-nothing per path**, which is what makes the URL
layout a decision rather than a detail. An app that may ever share part of
itself should keep shareable routes under their own prefix from the start, so
that opening them up later is an Access policy edit rather than a redesign. The
same applies in reverse to a `public` app: put the write surface under its own
prefix and protect that, or a public hostname is a public editor.

**`bin/check-exposure` asks the question in both directions.** For each
declared prefix it probes the prefix itself and asserts the Access redirect is
there — and then probes the prefix's **parent** and asserts it is not.

The second one catches a policy that is too *wide*. An Access rule written as a
path prefix is one typo from covering `/api` instead of `/api/edit`, and the
result is a fully working application nobody can read without signing in: every
container healthy, the hostname answering, the declared prefix gated exactly as
the registry says. The person who finds out is whoever opens the site on a
phone.

The parent is **derived**, by stripping the last segment, rather than declared.
A list of an app's read paths would be a second list to drift, and a check
asserting a stale set goes green against paths nobody serves any more — worse
than no check. A single-segment prefix derives `/`, which the hostname probe
already covers.

Measured against production on 2026-09-20:

```
food: /api/edit gated by Access, as declared (302)
food: /api ungated, so the gate on /api/edit is not too wide (404)
```

The `404` there is food's own router refusing an unregistered `/api/...` path,
not a gate — which is exactly why this keys on the **redirect** and never on
the status code. That path will answer `405` or `422` as the app grows, and the
check will not notice.

**Moving an app from `cloudflare-access` to `public` moves the gate from
Cloudflare into code.** The app's own visibility checks must already work
before that change lands — and be tested for *refusal*, with fixtures that make
refusal possible, because a check over an empty set passes without ever firing.

## What an app's CI needs

An app whose tests touch PostgreSQL — which is any app with a from-zero
migration test — needs a **service container in its workflow**, and a job-level
`env:` block to go with it. `ubuntu-latest` has PostgreSQL installed but not
running, and the runner has no `.env`, so without both the app's defaults apply
and authentication fails even once the service is up. The symptom is a required
check that can never go green, discovered on the first pull request.

`cg1618-apps/travel`'s workflow is the worked example.

Two more steps belong there for the same reason — they guard things a deploy
would otherwise discover: building the frontend (a bundle that does not compile
should fail the pull request, not the deploy) and `shellcheck` on any shell the
app ships.

## Development ports

Every app must be runnable at the same time on one laptop, so the ports are
derived rather than remembered:

**uvicorn = the app's registry port. Vite = 5173 + (port − 8000).**

| App | uvicorn | Vite |
| --- | --- | --- |
| `media` | 8000 | 5173 |
| `food` | 8001 | 5174 |
| `travel` | 8002 | 5175 |
| `art` | 8003 | 5176 |

`media` keeps the ports it has always had, which is what the rule was fitted
to. Two things each app's dev setup must do, because the failure modes are
quiet:

- **Refuse to start when its port is taken**, rather than falling back to the
  next one. A dev server that quietly takes 5176 has taken `art`'s slot, and
  two apps then fight over one port with nothing saying so. Vite needs
  `strictPort: true`; uvicorn needs the launcher to check first.
- **Proxy `/api` to its own uvicorn port**, not to 8000. A copied config that
  still points at `media` returns another app's data, which looks like a bug in
  this one.

## Development databases

One PostgreSQL container on the laptop with **one database per app**, named
after the app. That mirrors production, where one container holds one database
per app, and it avoids running four containers to develop four applications.

**It belongs to the platform**, not to any app: `docker-compose.dev-db.yml` in
this repository, container `cg1618-dev-db`, volume `cg1618_dev_pgdata`, started
by `.\dev-db.cmd`. Each app's `dev.ps1` brings that project up rather than
owning a compose file of its own.

```bash
.\dev-db.cmd                                         # start it
docker exec cg1618-dev-db createdb -U postgres travel  # add an app's database
```

It used to be `anime_site_postgres_db` inside **media's** compose project, and
the name was the smaller half of that problem. The real defect was ownership: a
`docker compose down` in any media tree removed the server every other app was
using. A project of its own is what makes that impossible; see
[notes/decisions.md](notes/decisions.md), "The development database belongs to
the platform".

The consequence to respect is the same one production has: a migration run in
one app's tree cannot affect another's database, but they share a server, so
stopping the container stops all of them.

**Per-app containers are a live option and were deliberately not taken here.**
The prize would not be isolation — apps are already isolated by database, and
nothing an app does can now touch the server — it would be **parallel test
runs**, since the machine-wide pytest lock exists precisely because four apps
share one server. The cost is a port and a postgres process per app, dev
diverging from production, and a lock that has to become per-app in the same
instant across five repositories or two sessions take different locks and run
concurrently, which is the failure the lock exists to prevent. If it is ever
done, the services are added to `docker-compose.dev-db.yml` as `db-media`,
`db-food` and so on.

## Adding an application

1. A pull request to this repository adding its `apps.yml` entry, with
   `status: planned`. The hostname, port and database are reserved from that
   moment; nothing is routed yet.
2. `bin/provision <app>` once, when it exists.
3. A new repository in `cg1618-apps` satisfying **the app contract**. Every
   item is something `bin/deploy`, `bin/health` or `bin/rollback` assumes, and
   an app that differs fails in a way that says nothing about the cause:

   - **A container on the port this file assigns**, answering the
     `health_path` declared here.
   - **`docker-compose.prod.yml` at the repository root.** All three scripts
     name that exact path — `bin/health` refuses outright when it is missing,
     which at least says so; `bin/deploy` and `bin/rollback` reach it through
     compose and fail later and less clearly.
   - **The app's image is built as `<app>-app:local`.** `bin/deploy` tags the
     outgoing image `<app>-app:previous` before it pulls, and `bin/rollback`
     swaps that tag back. An app whose service builds to some other name
     prints "no current image - first deploy" on **every** deploy and freezes
     on **every** rollback, with nothing else wrong and nothing pointing at
     the name.
   - **`DATABASE_URL` from the environment**, and a `main` branch that is
     production.
   - **A `production` environment in the app's repository, with the owner as a
     required reviewer.** This is the approval gate the deploy workflow's
     migration lane waits at, and it is the only item of the contract that
     exists nowhere in either repository's files. Referencing an environment
     that does not exist **does not fail**: GitHub creates it on first use,
     with no protection rules, and runs the job immediately — so an app that
     skipped this would deploy a schema migration unattended, in a green run,
     with the gate present in the workflow and meaning nothing.

     `bin/provision` arms it, and prints the command rather than failing when
     `gh` is missing or not logged in on the box. To do it by hand — and it
     must be this command, reviewers included, because a bare `PUT` creates
     the environment with **zero** protection rules, which is exactly the
     state this item exists to prevent:

     ```bash
     gh api -X PUT repos/cg1618-apps/<app>/environments/production        -F 'prevent_self_review=false'        -F 'reviewers[][type]=User' -F "reviewers[][id]=$(gh api user --jq .id)"
     ```

     `-F` rather than `-f` on every one of them: `-f` sends each value as a
     JSON string, and `prevent_self_review` is a typed boolean, so the API
     answers 422.

     **Both halves of this have now been observed rather than read.** The
     `PUT` was run on 2026-09-20 against `cg1618-apps/platform`, a repository
     with no environments at all, and created one from nothing:

     ```
     before  {"count": 0, "names": []}
     after   {"name":"production","rules":[{"type":"required_reviewers",
              "prevent_self_review":false,"reviewers":["cgentle1618"]}]}
     ```

     — then deleted again, because the platform has no deploy workflow and
     should not carry an environment. It was tested there rather than on an
     app precisely so that no app's gate was disarmed, even for seconds.

     And `verify-gate`'s `GET` of the same endpoint ran for real in `food`'s
     and `travel`'s releases, both of which took the gated lane and reported
     `verify-gate: success`. Neither call is reasoning from documentation any
     more. The workflow's `verify-gate` job asks the API
     whether the environment really has required reviewers and refuses the
     deploy when it does not, so an app that was never armed fails loudly
     instead of deploying.
   - **An executable `deploy/migrations` if — and only if — its `apps.yml`
     entry says `migrations: true`.** The two must agree: `bin/deploy` refuses
     when the registry declares migrations and the commit being deployed
     carries no runnable hook, and refuses just as loudly when it declares none
     and a hook exists anyway.

   `deploy/migrations` is how the platform asks an app about its own schema,
   because reading a version table, deciding what a deploy adds and reversing a
   migration are all specific to the tool an app chose. It answers three
   subcommands:

   - **`current`** prints the revision the database is at, read from the
     database rather than from the image. **An app whose schema has never
     been migrated has no version table at all, and the answer there is
     `base`, not an error** — that is every app's first deploy, and a hook
     that fails instead refuses the very deploy that would create the schema.
     `base` is Alembic's name for the point before the first revision and a
     real `downgrade` target, so a rollback recorded against it reverses the
     whole schema and restores a dump that was taken empty.
   - **`added <from> <to>`** lists the migration files a deploy would add, and
     prints nothing when there are none. Printing nothing and failing are
     opposite answers: the platform refuses on a non-zero exit rather than
     reading it as "none".
   - **`downgrade <target>`** reverses to that revision, and **must refuse —
     non-zero, having reversed nothing — any revision whose author declared it
     irreversible.** This is the one part of the contract that protects data
     rather than availability. Reversing such a migration does not restore
     what it removed; it invents something in the shape of it, and it does so
     unattended, on the box, in the minute after a failed deploy. A partial
     downgrade is worse again, because the schema then matches neither image.

     The media tracker's marker is the literal line `irreversible = True` in
     the revision file, and its hook greps the revisions between the current
     head and the target for it before running anything. Another app may mark
     it another way; what the platform requires is that the hook knows the
     marker and stops.

   **On a `--ci` deploy the hook is read from the commit being deployed, not
   from the checkout on the box.** Both questions asked before the pull are
   about the incoming code, and the outgoing hook has no better claim on
   either: `added HEAD origin/main` asks which revision files arrive, and
   `current` asks the database, which no version of the hook changes. Reading
   the checkout's copy instead breaks two things that matter — an app's first
   deploy, whose checkout was cloned to provision it and so predates its own
   hook, and any fix TO a hook, which would have to be carried to the box by
   hand before the run that ships it could use it. `bin/deploy` writes the
   incoming copy to `deploy/.migrations-incoming` beside the real one, because
   the hook finds its app root from its own path, and removes it on exit. A
   manual run has no such gap and uses the checkout in front of you.

   The hook is called with **`PLATFORM_DIR` exported**, naming the platform
   checkout. A hook that needs the shared PostgreSQL — `current` does — reaches
   it through `${PLATFORM_DIR}/docker-compose.prod.yml` rather than guessing a
   path that is right until the checkout moves. `bin/deploy`, `bin/rollback`
   and the workflow's `classify` job all export it.

   **`added` must answer from the git checkout alone — no database, no
   containers.** Only `current` and `downgrade` may touch the database.
   `added` is asked on a **GitHub-hosted runner** as well as on the box, where
   there is no PostgreSQL, no compose project and no `.env`. The first app
   whose `added` shells into compose would fail there on every push, `classify`
   would gate on the failure, and every one of that app's deploys would need
   an approval for good — correct, in a green run, and permanent.

   An app whose entry says `migrations: false` has no hook and needs none:
   `bin/deploy` skips both the recorded revision beside the dump and the
   approval gate, and `bin/rollback` goes straight to the image swap.

   - **A deploy workflow that calls the platform's, and does nothing itself.**
     `.github/workflows/deploy.yml` in the app repository is one decision and
     nothing else — copy it exactly:

     ```yaml
     name: Deploy

     # main only. main is production, and the box's checkout of this app
     # tracks main, so this trigger and that checkout are the same decision
     # stated twice.
     on:
       push:
         branches:
           - main

     jobs:
       deploy:
         uses: cg1618-apps/platform/.github/workflows/deploy-app.yml@main
         with:
           app: travel
     ```

     `app:` is the name spelled exactly as this file spells it; everything
     else — the classify job, the approval gate, the per-app concurrency
     group, the exit-2-only rollback — lives in the reusable workflow and is
     not an app's to restate. One optional input exists, `runs_on`, a JSON
     array of runner labels. A checkout that is not at `<apps dir>/<name>` is
     the registry's `path:` key, not a caller's input — see above.

     **The app's workflow must not name the self-hosted runner itself**, and
     must not carry a `pull_request` trigger anywhere near this job. The
     reusable workflow is `workflow_call` only for that reason; a caller that
     adds a trigger of its own hands the same catastrophe back.

     **Nothing enforces that, and it is worth being exact about why.**
     `tests/test_deploy_workflow.py` can only read the workflows in *this*
     repository; the platform cannot see, let alone fail, what an app repo
     commits. A fork's pull request against an app repository runs in the base
     repository's context, so a `pull_request` trigger there would reach the
     box. Today the rule is **honour-system: a line in this document and a
     line in the workflow's header comment.**

     Three things would actually enforce it, none of them done:

     - a **runner group restricted to selected repositories**, so a repo that
       was never listed cannot resolve the `homelab` label at all;
     - an **organisation Actions policy requiring approval for all outside
       collaborators**, so a fork's pull request does not run unattended;
     - **shipping the trigger test to app repositories** as a reusable CI
       workflow, so each app fails its own pull request the way the platform
       fails its own.

     The first two are settings rather than code, and the third is the only
     one this repository can make true by itself.

4. When it can actually serve, one line: `status: live`. That is the change
   that routes its hostname and links it from the apex page.

It never touches `media` or any other app.

## Protection

`main` and `dev` are covered by the `Protected Branches` ruleset: deletion and
force-push blocked, a pull request required, and `test` a required status check
with "branches must be up to date" on.

This has been observed refusing, not merely configured — a direct push to `dev`
is rejected server-side, naming both rules:

```
remote: - Changes must be made through a pull request.
remote: - Required status check "test" is expected.
```

Worth keeping in mind that a passing check and a mergeable pull request look
exactly the same whether the ruleset is attached or absent. The rejection above
is the only observation that distinguishes them.

## The workflow runs on GitHub, never on the box

`.github/workflows/ci.yml` triggers on `pull_request` and runs on
`ubuntu-latest`. **No `pull_request`-triggered job may ever name the self-hosted
runner**, here or in any application repository: every repository in this
organisation is public, the runner is a machine in a house, and a fork's pull
request executing on it is the standard catastrophe. It is the single most
important line to review in a new app's deploy workflow.

## How a deploy runs

A merge to an app's `main` triggers its `deploy.yml`, which calls the
platform's reusable workflow. The workflow classifies the push and picks one
of two lanes:

- **Ungated** — the push adds no migration. It deploys immediately, with no
  approval.
- **Gated** — the push adds one or more revision files. It waits for the
  owner's approval in the `production` environment first, and a separate
  `verify-gate` job asks the API whether that environment really has required
  reviewers. An environment that was never armed is created silently with zero
  protection rules, which looks identical to a working gate.

The classification is re-checked on the box against its own `HEAD`, because a
runner that was offline across two merges sees a push range that misses the
earlier one.

### Exit codes, and the difference between them is load-bearing

`bin/deploy` exits:

| code | meaning | what the workflow does |
| --- | --- | --- |
| 0 | deployed and healthy | nothing |
| 1 | **refused to start** — wrong branch, no `.env`, an unapproved migration, a registry and repository that disagree | nothing. Production was never touched and is still serving |
| 2 | the deploy **ran** and the result is unhealthy | `bin/rollback` |

`if: failure()` alone cannot tell 1 from 2, and rolling back an exit 1 would
take a working site down to recover from nothing. The workflow captures the
code and gates the rollback on `rc == 2`.

`bin/rollback` does not exit 2. When it cannot proceed safely it **freezes**:
it stops, prints the dump path, both recorded revisions and the manual
procedure, and leaves the box as it is. A rollback that half-succeeds is worse
than one that stops.

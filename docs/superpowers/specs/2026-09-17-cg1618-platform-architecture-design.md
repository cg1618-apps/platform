# Multi-app structure: git topology and the platform repo

Status: design approved in discussion, not yet executed.
Written 2026-09-16, against `origin/dev` at `afa687f2`; extended 2026-09-17 with
the verification, deployment, provisioning and ordering decisions.

**What this decides.** How seven personal applications — one of which exists —
are organised in git, what the box's shared infrastructure belongs to, and how
concurrent development across them works. It does not decide the applications
themselves.

This spec lives in the media tracker repo because that is currently the only
repo. Executing it moves most of what it describes out.

## Context

[deployment-selfhost.md](../../deployment-selfhost.md) already fixes the network
layer: seven apps, one box, one domain, one subdomain and one local port each —
`media` 8000, `art` 8001, `food` 8002, `journal` 8003, `health` 8004, `money`
8005, `travel` 8006 — routed by a single `cloudflared` daemon, with the apex
undecided. Only the media tracker exists.

Two constraints from the owner shape everything below:

- **The apps share nothing** — no accounts, no data, no common library. Sharing
  may be revisited when a second app is actually being designed.
- **Development will be concurrent** — several apps worked on at the same time,
  in separate Claude Code sessions.

The problem this spec exists to solve is that the media tracker repo does not
only contain the media tracker. It owns the box: the tunnel ingress for all
seven hostnames, the PostgreSQL instance, the host's backup units, the deploy
scripts and the tunnel credentials. Adding a second app today would mean
committing to app #1 and redeploying it.

## Decision: polyrepo, with a platform repo as the master

| Repo                                     | Contains                                                                                                                                                    |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cg1618-apps/platform`                        | the master: `apps.yml`, the apex page, cloudflared ingress, the shared PostgreSQL, backup units, deploy scripts, box documentation, the generic `CLAUDE.md` |
| `cg1618-apps/media`                           | the media tracker, migrated from `anime_site` into a new repository with no git history, minus the box-level parts                                          |
| `cg1618-apps/{art,food,journal,health,money,travel}` | one repo each, created as each app is started                                                                                                        |

**The repos live in a GitHub organisation named `cg1618-apps`, not under the
`cgentle1618` user.** Organisations and user accounts share one namespace, so an
organisation cannot be called `cgentle1618` while that username exists — nor
`cg1618`, which a dormant personal account registered in 2025 and has never
used. The
organisation is what makes a single self-hosted runner and a single deploy
pipeline possible across eight repos — see "Deployment across repos" below —
and it is free at this scale.

### Naming: `cg1618` for the project, `cgentle1618` for the person

`cg1618` is the abbreviation of `cgentle1618`, and the choice between them was
already made once, for the domain: `cgentle1618.com` was free and was
considered, and `cg1618` won on length, because the string ends up in SSH
configs, `.env` files and tunnel config for years
([deployment-selfhost.md](../../deployment-selfhost.md)). That argument applies
with more force to repository URLs and directory paths, which are typed more
often than a hostname is.

So the project is `cg1618` in every namespace it owns — the domain
`cg1618.com`, the local root directory `Documents\cg1618\`, and each app's
subdomain. Databases and roles are named for the app alone (`media`, `art`),
scoped by the instance rather than by a prefix. The SSH alias stays `homelab`:
it names the machine, not the project.

**The GitHub organisation is the one exception, and is `cg1618-apps`.** Plain
`cg1618` is held by a dormant personal account — registered 2025-11-21, no
repositories, no activity since the minute it was created — and GitHub gives
users and organisations one namespace. The suffix costs almost nothing, because
this is the least load-bearing name in the system: an organisation name appears
in clone URLs and the runner registration URL and nowhere else. It is not in the
domain, the SSH config, any `.env`, or the tunnel configuration — which is what
the length argument above was actually about.

`cgentle1618` remains the **person** — the account handle, the commit author
identity, the required reviewer on the `production` environment, and the
archived repository URL that old pull request links resolve to. That split is
what organisations are for, and an organisation name differing from its owner's
username is the ordinary case rather than a compromise.

The master repository is `cg1618-apps/platform`. `platform` is broader than
`infra` in the way the contents require: it holds the apex page as well as the
ingress and the database.

**Every repo is public**, and that is a decision rather than inertia. On the
free plan GitHub grants two things only to public repositories, and the pipeline
depends on both: **environments with required reviewers**, which is the whole
mechanism of the migration approval gate — *"Users with GitHub Free plans can
only configure environments for public repositories"* — and **repository
rulesets**, which is what makes a CI check required rather than merely
conventional. A private repo on a free organisation loses the first for certain
and the second in all likelihood; restoring them means paying for GitHub Team.
The consequence is that the self-hosted runner rule in "Deployment across repos"
is load-bearing security, not hygiene.

**`cg1618-apps/media` is a new repository, not a rename or a transfer.** The
working tree is committed fresh; the 2,238 commits and 216 pull requests of
`cgentle1618/anime_site` do not travel. That repo is **archived read-only rather
than deleted**, so its pull request discussions stay readable at their existing
URLs, but nothing in the new repo points at them and no history command reaches
them. Design rationale that is still load-bearing must therefore be in `docs/`
before the migration, not left implicit in a commit message — this is what
`docs/notes/` exists for.

`app-template` is **not** in this table. A skeleton cannot be extracted from a
stack that has not been chosen, and extracting one from the media tracker would
make FastAPI + React the default for every later app by accident, which is
precisely the question being left open. It is built from app #2's real shape,
once that shape exists.

The master repo connects the sub-projects by **configuration**, not by git
pointers. It knows about the seven apps; it does not contain them.

**Rejected: a monorepo.** `HEAD` belongs to the working tree, so seven
concurrently-developed apps in one repo means seven permanent worktrees, each
paying the full `worktree.ps1` setup — the cost concurrency makes worst. It
would also mean rewriting every path in `dockerfile`, `alembic.ini`,
`pytest.ini`, `dev.ps1`, `worktree.ps1`, `.github/workflows/ci.yml` and most of
`docs/`, and either path-filtered CI or seven suites on every pull request. Its
advantages — cheap code sharing and atomic cross-app commits — are the ones the
owner explicitly does not want yet.

**Rejected: git submodules.** The parent pins a child sha, so every app change
becomes two commits forever, with an ordering constraint between them — the
stacked-PR failure this project has already been bitten by, made structural.
Submodules also check out at a detached `HEAD` by default, which is the same
class of hazard as the shared-`HEAD` problem the worktree rules exist to
prevent, and `git clone` without `--recursive` fails quietly. Submodules are a
vendoring tool; Android's `repo` and its manifest exist because they did not
scale to "many repos, one product".

**Rejected: leaving infrastructure in the media tracker.** Free today, and it
makes `media` a privileged repo that every other app's deploy must touch. This
is the status quo extended, and the failure the question exists to avoid.

**The cost accepted.** No single commit describes the whole platform at a
moment, and a convention change is eight pull requests rather than one. Both are
tolerable because the apps deploy independently as separate containers on
separate ports. If a platform-wide version stamp is ever wanted, `apps.yml` can
carry each app's deployed version.

## Local layout

```
Documents\cg1618\              clone of cg1618-apps/platform; root for cross-app work
    CLAUDE.md                  generic rules (git, concurrency, docs discipline) and the box
    CLAUDE.local.md            per-machine notes for the box (gitignored)
    apps.yml
    apex/  bin/  cloudflared/  postgres/  backup/  docs/
    .gitignore                 /media/, /art/, /food/, ...
    media\                     clone of cg1618-apps/media, its own git history
        CLAUDE.md              media-specific only
        CLAUDE.local.md        per-machine notes for media (gitignored)
    food\                      clone of cg1618-apps/food
        CLAUDE.md
```

Each app directory is gitignored by the master, so the two histories never see
each other.

### Why nesting works

Claude Code's memory loading is a filesystem rule, not a git rule, so it is
unaffected by the repo boundary. Verified against the Claude Code documentation
on 2026-09-16:

- `CLAUDE.md` and `CLAUDE.local.md` are loaded from the working directory **and
  every directory above it**. A session started in `cg1618\media\` therefore
  gets the master's file and the app's.
- Discovered files are **concatenated, not overridden**, ordered from the
  filesystem root down. The master loads first and the app last, so an app rule
  wins a conflict by default. Within a directory, `CLAUDE.local.md` follows
  `CLAUDE.md`.
- Files in **subdirectories load on demand**, when Claude reads files there. A
  session started at `cg1618\` stays light until it touches an app.
- `claudeMdExcludes` in `.claude/settings.local.json` skips an ancestor file by
  glob, if a master rule ever gets in an app's way.
- Auto memory keys its directory off the git repository, so each app repo gets
  its own memory directory rather than pooling all seven.

This is what makes the generic rules single-source without a submodule and
without copying. It is also an opportunity to fix a real problem: the current
`CLAUDE.md` is 668 lines against a documented 200-line target, and roughly half
of it — the git workflow, the concurrency rules, the documentation discipline —
is box-wide rather than media-specific. Split, both files land near target.

## `apps.yml`: one source of truth

```yaml
apps:
    - name: media
      hostname: media.cg1618.com
      port: 8000
      database: media # null is legal: an app need not have one
      repo: git@github.com:cg1618-apps/media.git
      exposure: public # public | cloudflare-access | lan-only
      health_path: /api/health
      description: Media tracker & database
```

`health_path` is there because the apps do not share a stack. `deploy.sh`
currently waits for `/api/health`, which is this application's answer rather
than a platform fact; an app written against something other than FastAPI may
expose a different path, so the app declares it and the deploy script reads it.

Derived from it, never hand-edited: the cloudflared ingress, the apex page's
navigation, the list of databases the backup job dumps, and a check that no two
apps collide on a hostname, a port or a database name. The generated files are
**committed**, and CI regenerates them and fails on a difference — see
"Verification" below. This promotes the
"Planned hostnames" table in `deployment-selfhost.md` from prose into
configuration, and moves the `exposure` decision for `journal`, `health` and
`money` — currently an open item — into the place the ingress is generated
from, which is where that document already says it belongs.

## The app contract

The apps do not share a stack. Python and PostgreSQL are likely; FastAPI and
React + Vite are not decided, and nothing here should decide them by accident.
So the platform requires four things of an application, none of which names a
framework:

1. **A container that listens on the port `apps.yml` assigns it**, publishing
   nothing to the host.
2. **A health path it declares** in `apps.yml`, answering 200 only when the
   application can actually serve — for the media tracker that means opening a
   real database session, which is why `/api/health` exists rather than the
   catch-all route.
3. **`DATABASE_URL` read from the environment**, if it has a database at all.
4. **A `main` branch that is production**, moving only by pull request.

Everything else — language, framework, migration tool, whether there is a
frontend build at all — belongs to the app. Where the current pipeline assumes
otherwise, the assumption becomes a declared value rather than a hard-coded one:
`health_path` in `apps.yml`, and `migrations_path` as an input to the deploy
workflow, replacing `classify`'s hard-coded `^alembic/versions/` grep.

## What moves, and what stays

| Moves to `cg1618-apps/platform`                                                                      | Stays in `media`                                              |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `deploy/cloudflared/config.yml`                                                        | `dockerfile`, the `app` service definition                    |
| `deploy/backup/` — systemd units, dumps                                                | `docker-compose.yml`, the development PostgreSQL              |
| `deploy/deploy.sh`, `rollback.sh`, `health.sh`, parameterised by app name              | `alembic/`, `app/`, `frontend/`, `tests/`, `static/`          |
| the `db` and `cloudflared` services of `docker-compose.prod.yml`                       | the `app` service, joining an external network                |
| `TUNNEL_ID`, `CLOUDFLARED_CREDENTIALS`, the PostgreSQL superuser credentials           | an app-scoped `.env`: its own database role, its own API keys |
| `deployment-selfhost.md`, `setup-selfhost.md`, `deploy/README.md`, `deployment-gcp.md` | the rest of `docs/`                                           |
| the generic half of `CLAUDE.md`                                                        | the media-specific half                                       |

`bin/deploy <app>` keeps the property that matters in the current script: it
dumps the database before it pulls.

## PostgreSQL: one container, one database and one role per app

Not seven containers. The backup machinery — `pg_dump`, the systemd timer, the
`flock` that serialises it against a deploy — already exists and would otherwise
be duplicated seven times. The apps share no data, so isolation at the database
level is sufficient. Each app's `.env` holds a role that can reach only its own
database; the superuser credential lives in `cg1618-apps/platform` alone.

The alternative, a container per app, buys independent version upgrades and a
smaller failure domain for roughly seven times the backup configuration. It is
the change to make if a single instance ever becomes the thing that hurts.

## Provisioning: `bin/provision <app>`

Creating a database and a role is rare, privileged and needs the PostgreSQL
superuser credential. Deploying is frequent. Keeping them apart is the reason
provisioning is its own command rather than a step inside `bin/deploy`: folding
them together would give every routine deploy superuser rights over every app's
data.

`bin/provision <app>` reads `apps.yml` and is idempotent, so re-running it is
safe:

- create the database named in the entry, unless it exists;
- create a role with a generated password, unless it exists;
- `REVOKE CONNECT ON DATABASE <db> FROM PUBLIC`, then grant it to that role
  alone, so no app can reach another's data even sharing one instance;
- write the password into that app's `.env` on the box.

No password is recorded in `apps.yml` or anywhere else in git. An app whose
`database` is `null` is skipped.

**Rejected: Terraform with the `postgresql` provider.** Declarative and
drift-detecting, and the right answer at a scale this is not. It adds a state
file that has to be stored, backed up and kept uncorrupted, in exchange for
managing seven `CREATE DATABASE` statements that change when an app is added and
never again.

## Verification

`cg1618-apps/platform` gets its own `Tests` workflow on every pull request, and
the repository ruleset makes it a required check on `dev` and `main` — the same
arrangement as the media tracker, for the same reason: the ruleset is what makes
the gate real rather than conventional.

What it checks:

- **`apps.yml` against a JSON Schema.** Shape, required fields, the `exposure`
  enum.
- **Policy, which a schema cannot express.** No two apps share a hostname, a
  port or a database name; `journal`, `health` and `money` are never `public`.
- **That the generated files match their source.** CI regenerates the ingress
  and the apex navigation from `apps.yml` and fails if the committed output
  differs. The generated files stay committed, so the ingress that will be
  deployed appears in the pull request diff where a human reads it.
- **`actionlint`** on the workflows, **`shellcheck`** on `bin/*.sh`.

**The same validator runs again inside `bin/deploy`.** Shift the check left, but
do not trust that it ran — the shape `deploy.sh` already has, re-checking
`MIGRATION_APPROVED` on the box rather than believing GitHub's gate.

This replaces a guard that would otherwise be lost. Today the only thing
stopping `journal.cg1618.com` from being routed by accident is
`tests/unit/test_prod_compose.py`, which reads `deploy/cloudflared/config.yml`
from inside the media tracker's suite. Moving that file without moving its guard
would quietly delete the protection.

## Deployment across repos

One organisation, one runner, one pipeline definition.

- **The self-hosted runner registers at the organisation level**, not per
  repository, so the box runs one runner service rather than eight. Every
  organisation gets a single default runner group; only additional groups need a
  paid plan, and one group is all this needs.
- **The pipeline lives once, in `cg1618-apps/platform`**, as a `workflow_call`
  reusable workflow: the classify step, the two lanes, the `production`
  environment gate, the exit-2-only rollback. Each app repo's deploy workflow is
  a few lines that call it with its own app name, `migrations_path` and health
  path. Eight consumers, one definition, versioned by tag.
- **No `pull_request`-triggered job may run on the self-hosted runner, in any
  repo.** The repositories are public by necessity (see the decision above), and
  a fork's pull request running on a machine in the house is the standard
  catastrophe. The current arrangement is already safe — `ci.yml` runs on
  `ubuntu-latest`, and `deploy.yml` triggers on `push` to `main`, which a fork
  cannot cause — but it is safe by accident of how it was written rather than by
  rule. It becomes a stated rule every repo inherits, and the one line in a new
  app's deploy workflow most worth reviewing.
- **Concurrency is per app**, `group: deploy-<app>`, never cancelling in flight,
  so two apps can deploy at once and one app cannot deploy over itself.

**Rejected: `repository_dispatch` into a central deploy repo.** Keeps one runner
without an organisation, at the cost of a cross-repo personal access token and a
classify step that has to read a diff belonging to another repository.

**Rejected: a runner and a copy of the pipeline per repo.** Eight runner
services to keep alive on one mini PC, and eight copies of a pipeline that will
drift.

## The apex page

`cg1618.com` serves a static page listing the apps, built from `apps.yml`,
served by a small container on port 8007, with its source in `platform/apex/`.

It sits in the master repo rather than a repo of its own because it is not an
application but a rendering of the registry: its content is `apps.yml`, and it
changes exactly when `apps.yml` changes, so it has no independent deploy
cadence. This is the ordinary homelab-dashboard arrangement.

**Graduation rule.** The first time the apex page needs a backend, a database,
authentication or per-user state, it becomes `cg1618-apps/landing` with its own
repo and its own port. That rule is what keeps "no application code in the
infrastructure repo" honest rather than arbitrary.

## Workflow

- **Sessions.** One at `cg1618\` for infrastructure and cross-app work; one
  inside each app directory for that app. All concurrent. Separate repos mean
  separate `HEAD`s, so no worktree is needed for one session per app. Worktrees
  return to their real purpose: two sessions on the _same_ app.
- **Shipping an app.** `<type>/<topic>` off that app's `dev` → pull request →
  that app's `dev` → pull request → that app's `main`, and the merge to `main`
  deploys itself through the shared reusable workflow. Two pull requests, both
  inside the app repo; `bin/deploy <app>` is what the pipeline runs, not
  something typed by hand. `cg1618-apps/platform` has its own `dev` and `main`
  under identical discipline, carrying infrastructure changes.
- **Adding an app.** One pull request to `cg1618-apps/platform` adding an
  `apps.yml` entry, from which the ingress, port and database follow; then
  `bin/provision <app>` once; then a new repo satisfying the app contract. It
  never touches `media` or any other app.
- **Nothing in git mentions AI.** The existing rule is box-wide and moves to the
  master `CLAUDE.md` unchanged.

## Deliberately not decided here

These belong to the development-workflow discussion, not to the git topology:

- The machine-wide pytest lock, which must remain one lock across eight repos
  rather than one per repo.
- Development port allocation on a laptop — uvicorn and Vite, per app.
- Whether the one development PostgreSQL is shared across app repos the way the
  production one is.
- What `app-template` actually contains. This is **blocked rather than
  deferred**: the stack is undecided, and a skeleton cannot be extracted from a
  stack that has not been chosen. It is built from app #2's real shape.
- Which stack each app uses. Python and PostgreSQL are likely; FastAPI and
  React + Vite are open. Nothing in this spec decides it, which is what "The app
  contract" above exists to guarantee.

## Execution order

Four steps come before app #2 exists, because they are what production depends
on and what is expensive to change once a second app is running. The rest
follows alongside it.

1. **Create the `cg1618-apps` organisation, create `cg1618-apps/media` as a new
   public repository, migrate the working tree into it with no history, re-register the
   runner at organisation level, and archive `cgentle1618/anime_site`
   read-only.** One operation, because each part of it rewrites `origin` — on
   both development machines and on the box — and because the box must not be
   left pointing at an archived remote. Everything GitHub held rather than git
   is recreated by hand here: the branch ruleset, the `production` environment
   and its required reviewer. The stale `GCP_CREDENTIALS` secret is not carried
   over.
2. **Create `cg1618-apps/platform`**: `apps.yml`, its schema, the validator, the
   `Tests` workflow, the ruleset. Nothing moves and nothing deploys, so this
   step cannot break production.
3. **Split the running stack.** `db` and `cloudflared` move to the platform
   repo; `media` keeps only `app`, joining an external network. This is the one
   step that restructures live production, and it needs a database dump taken
   first and a rehearsed way back.
4. **The reusable deploy workflow**, `bin/deploy` and `bin/provision`. After 3,
   because their shape depends on the split.

**The apps are built in the order `food`, `travel`, `art`**, and the first three
are deliberately all `public`: none of them needs a Cloudflare Access policy, so
the contract can be proven end to end without a decision that lives outside this
repository. `journal`, `health` and `money` come after, when the Access path is
worth building once.

Then app #2 - `food` - begins, and these follow alongside it:

5. Split `CLAUDE.md` into the generic and media-specific halves, and move the
   box documentation to the platform repo.
6. The apex page on port 8007.
7. `app-template`, extracted from app #2 once its stack is real.

Starting app #2 after step 4 rather than after step 6 is deliberate: a second
application written in a second stack is the only thing that can prove the app
contract is actually stack-agnostic rather than FastAPI described in general
terms.

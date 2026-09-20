# Open items

Known defects and unmade decisions that nobody is currently working on.
Everything here is open by definition: there is no status column and nothing is
claimed. An item is closed by **deleting it in the same change that fixes it**,
and that commit is the record.

## The registry cannot express a gate on part of an app

`docs/registry.md` tells a `public` app to "put the write surface under its own
prefix and protect that, or a public hostname is a public editor". Nothing in
this repository can represent that, let alone check it:

- `exposure` is one enum for a whole app, and the schema is
  `additionalProperties: false`, so an app cannot even declare a gated prefix
  without a schema change here.
- `bin/generate_ingress.py` emits one rule per hostname. For
  `cloudflare-access` it writes a *comment* and nothing else — the Access
  application itself lives in a Cloudflare dashboard this repository cannot
  see.
- `bin/check-exposure` probes `https://<hostname>` and nothing below it. A
  `public` app answers ungated at the root, which is correct, and the check
  never asks about `/api/edit`. **So an unprotected write surface passes every
  check here** — the same vacuous-gate shape the root `CLAUDE.md` warns about,
  where the check that should catch it never reaches the thing that matters.

`food` is the first app this bites: it is `public`, and its own `CLAUDE.md`
requires writes behind Access on their own prefix. It is not blocking anything
today because food has no write routes yet, but it must be settled before
food's first write endpoint reaches `main`.

The decision is made — `docs/notes/decisions.md`, "A gated path is defined by
the app; the registry declares it and is checked". What remains is building it,
and none of it is urgent: food has no write routes, so nothing is exposed yet.

What is left to do, in the order it has to happen:

- `food` ships the definition — one constant its routers derive from, a test
  that enumerates routes and asserts every non-GET one sits under it (with a
  mirror case, since that test is vacuous on an empty route table), and a
  generated `deploy/gated-paths` asserted to match the constant. food owns
  this and is building it in the same pull request as its first write
  endpoint, not before: the prefix string is still an open design question
  there, and committing it now would enshrine a value nobody has chosen.
- ~~The platform half~~ — **built**. `gated_paths` is in the schema,
  `bin/validate_apps.py` refuses it on a non-`public` app and on `/`,
  `bin/deploy` refuses when the registry and the app's `deploy/gated-paths`
  disagree in either direction, and `bin/check-exposure` probes each declared
  path for the Access redirect.

**Both halves are now in place.** The Access application covering
`food.cg1618.com/api/edit` exists, and `apps.yml` declares the prefix.
Measured from the open internet rather than from a dashboard: `/api/edit` and
`/api/edit/ingredients` answer 302 to `cg1618.cloudflareaccess.com`, while
`/`, `/health`, `/api` and `/api/ingredients` answer ungated — so the policy is
neither too narrow nor too wide.

**One window is open and it is inherent to two repositories.** `food` ships
`deploy/gated-paths` on its `dev`, not yet on `main`, so until its release
lands `bin/deploy` refuses a food deploy: the registry declares `/api/edit` and
`origin/main` declares nothing. That is the two-PRs-in-sequence cost the
polyrepo decision already names, and it cannot be avoided - the two halves live
in two repositories and cannot land in one commit.

The order was chosen to put the window where nothing happens. Declaring now
blocks deploys of a skeleton `main` nobody deploys. Declaring after the release
merged would instead refuse **the release itself**, at the moment somebody is
waiting on it. If a food deploy is needed before the release, the answer is to
land the release, not to remove the declaration.

~~There is no Cloudflare Access application covering
`food.cg1618.com/api/edit`.~~

`food` shipped `deploy/gated-paths` containing `/api/edit` and enforces it in
its own CI. `apps.yml` deliberately does **not** declare it yet, and the order
matters:

1. Create the Access application covering `food.cg1618.com/api/edit`. This is
   dashboard work and it is the only step that makes the gate real.
2. Then add `gated_paths: ["/api/edit"]` to food's `apps.yml` entry.

Declaring it first was tried and reverted. With the declaration in place and no
Access application, `bin/check-exposure` correctly fails — it was measured, not
predicted: `food: /api/edit IS DECLARED GATED BUT ANSWERS 404 UNGATED`, exit 2.
That would block **every** food deploy, including ones carrying no write routes
at all, to protect a prefix that does not yet exist on `main`. A gate that
refuses deploys for a surface nobody serves is a speed bump.

Leaving the registry silent does not lose the protection, because `bin/deploy`
refuses the moment the app ships `deploy/gated-paths` and the registry does not
declare it. That refusal fires exactly when food's writes reach `main`, which
is exactly when the Access application has to exist. The enforcement is in the
ordering rather than in an early declaration.

## Three apps have no `docs/` shaped like `media/docs/`

`CLAUDE.md`'s "House style" section requires every feature, rule and behaviour
to be documented as Markdown in that app's `docs/`, shaped like `media/docs/`,
landing in the same commit as the behaviour change. That rule landed in #48 and
is right. It also declares three apps short the moment it was written:

| App | Markdown pages under `docs/` |
| --- | --- |
| `media` | 34 |
| `food` | `README.md`, `api.md`, `data-model.md`, `deployment.md`, `frontend.md`, `testing.md`, `notes/` |
| `travel` | 4 (`README.md`, `notes/`, and live `superpowers/` scaffolding) |
| `art` | 2 (`README.md`, `notes/`) |

**`food` has largely answered this for itself**, and the answer settles the
open question below in favour of pages-on-demand: every one of those pages was
written with the behaviour it describes, in the same commit, and none of them
is a stub asserting nothing. `travel` and `art` are where the question is still
open.

**This is mostly not a backlog of unwritten pages.** `food`, `travel` and `art`
have almost no behaviour yet, and a page describing features that do not exist
is worse than no page — it is the abandoned-spec problem, written in the
present tense. Most of what `media/docs/` holds has nothing to describe in the
other three.

What is actually open is narrower, and it is a timing question:

- The three apps have no `docs/` **skeleton** to land a page into, so the first
  feature that ships has to invent the file name and the layout under time
  pressure, which is how four apps end up with four different documentation
  shapes — the exact divergence "House style" exists to prevent.
- `travel` is the live case and it is live **now**: the packing-lists work is
  nine tasks, and under the rule its documentation lands in the same commits,
  not afterwards. `travel/docs/` currently has nowhere obvious to put it.
- `food` is the cheapest case, being still at the skeleton, and is the one to
  get right first because nothing has to be retrofitted.

The decision nobody has made: whether an app creates its `docs/` pages
**empty-but-named** up front, mirroring `media/docs/`, or creates each page
with the first feature that needs it. Naming them up front makes the shape
obvious and the landing place unambiguous; it also produces a set of stub
files asserting nothing, which is its own kind of lie. Creating them on demand
avoids the stubs and risks the divergence.

Not urgent for `food` and `art`. It is urgent for `travel` only in the sense
that its first nine commits will establish a precedent either way, and a
precedent set by accident is the thing "House style" was written against.

Raised by the session that wrote #48, against its own change.

## Two calls in the deploy gate have never been executed

The migration-approval gate is built and merged, and two of its API calls are
still reasoning from documentation rather than observation. Neither has run
once:

- **`verify-gate` reads `GET repos/{owner}/{repo}/environments/production`**
  with `permissions: contents: read` and `${{ github.token }}`, and refuses
  unless the protection rules include `required_reviewers`. That this token
  and that scope can read the environments endpoint on a public repository is
  from the documentation. If it cannot, the job fails closed — which is the
  right direction, but it fails at the moment somebody is waiting on a
  migration deploy, and the error will look like a gate misconfiguration
  rather than a permissions one.
- **`bin/provision` arms the gate with `gh api -X PUT
  repos/<slug>/environments/production`**, needing a token that administers
  the app repository. It has never been run against a repository whose
  environment was not already armed. This one fails visibly: the `else` branch
  prints the exact command for a machine that is logged in, and provisioning
  continues, because by then the role, the database and the `.env` are
  written.

**The first migration deploy of any app exercises both**, and that is the only
thing that will. Nothing before it does: the gate is skipped entirely when
`classify` finds no migration, so every deploy so far has gone down the
ungated lane and proven nothing about this one.

**That first deploy is already on the way, and nobody scheduled it as a
test.** `travel` has `alembic/versions/0002_packing.py` on `feat/packing-lists`
and `food` has its ingredients revision on `feat/ingredients`; `origin/main`
holds only the baseline in both. So whichever of those two releases first is
the run that exercises these calls, and it exercises them during a release
rather than a rehearsal.

Not blocking. Worth knowing before the first migration goes out rather than
during it, and worth doing deliberately — arm an app's environment with
`bin/provision` on a repository that has none, and watch the first gated
deploy rather than discovering it under a release.

Recovered from a working report left by the step-4 deploy-pipeline round,
which was never in git and has been deleted. Its two other unverified claims —
SC2088 on the `bin/` scripts and the workflow parsing under `actionlint` — are
closed: `ci.yml` runs both on every pull request and has been green since.

## `art`'s first hand-named migration, and why three baselines are not evidence

`CLAUDE.md`'s "House style" already settles this — migration naming is one of
the conventions `media` is the reference for. What is open is that the evidence
on disk points the other way, and it has already misled two sessions in one
day.

`media` has nine revisions and every one is a mnemonic id:
`al1n2ilist_anilist_score_columns`, `s1r2rootflag_rename_is_superuser`,
`g1c2f3flags4_game_completion_vocabulary`. Not a sequential number among them.

`food`, `travel` and `art` each carry `0001_baseline.py`. **All three inherited
it from the same app skeleton, so it is one decision appearing three times, not
three apps agreeing.** Read as a pattern it is the most convincing wrong signal
in the repository: three of four apps, unanimous, and false.

It has already cost twice. `travel` named `0002_packing` by hand, following its
own baseline, and renamed it to `p1acking0001` once it read `media` — safely,
because the revision had never been released and the local database was
downgraded first, so no version row was stranded. The platform session nearly
flagged `food` for breaking the convention `food` was in fact the only new app
following, having read `media` rather than its neighbours.

**`art` is the one app where this is still ahead.** It has only the skeleton
baseline, so its first hand-named revision has not been written, and no session
is working on it. Whoever writes it should read `media/alembic/versions/`
first — the actual directory, not the pattern the other apps establish.

Renaming the three inherited baselines is **not** proposed. They are released
and applied, and a revision id that has been applied cannot be renamed without
stranding the row that records it; that is why the rule is reparent, never
renumber. The baselines stay, and what is written down is that they are
inherited rather than chosen.

## Nothing checks whether an Access policy is too WIDE

`bin/check-exposure` now asks whether each `gated_paths` prefix is gated. It
does not ask whether anything *else* got gated with it, and that failure is
quieter than the one it does catch.

**The failure, stated as a failure.** An Access policy written as a path prefix
is one typo from covering `/api` instead of `/api/edit`. The result is a fully
working application that nobody can read without signing in. Every container is
healthy, every existing probe passes if the policy starts below the root, and
the person who discovers it is whoever opens the site on a phone in a shop —
which is the case a `public` app exists for.

**Do not write down a list of an app's read paths.** `food` offered five, and
they would be wrong the moment module 2 lands: a check asserting a stale set
goes green against paths nobody serves any more, which is worse than no check.

The rule that does not rot is the complement of what `gated_paths` already
says. An app's invariant is "everything not under a gated path is public", so
the check is: **for each declared prefix, probe one path just outside it and
assert it answers ungated.** That parent can be derived rather than declared —
strip the last segment, so `/api/edit` probes `/api` — which means no new
registry key and no second list to drift. A single-segment prefix derives `/`,
which is already probed.

`food` also names one concrete path that will still exist in a year if a
literal is ever wanted: `/api/ingredients`, module 1's list endpoint, the first
thing the app ever served and not removed by anything later.

**The probe must key on the Access redirect, never on the status code**, which
the existing one already does and which matters more here. `food.cg1618.com`
answers `404` on `/api/edit` today because `app/main.py` refuses `/api/...`
explicitly rather than serving the SPA catch-all — the app deliberately saying
"no such route", not a dead container. After food's first release that same
path answers `405` or `422`, because the route will exist but a bare GET will
not match it. A check keyed on status would move under that transition; one
keyed on the redirect does not notice it at all.

Small to build, and it belongs in the same loop that probes the prefixes.

## `docker compose down` in any media tree destroys the shared database container

On 2026-09-19 the shared PostgreSQL container vanished from the home machine
and was reported as unexplained. It was not unexplained, and it was not a
crash. `docker events` holds the sequence:

```
22:37:03  kill → stop → die → destroy   anime_site_postgres_db
22:37:03  unmount                       anime_site_postgres_anime_data
22:38:47  create → start                anime_site_postgres_db
22:38:47  mount                         anime_site_postgres_anime_data
```

`kill`, `stop`, `die`, `destroy` in one second, with the volume **unmounted
rather than removed**, is the signature of `docker compose down` (or
`docker rm -f`). A crash gives `die` alone and leaves the container in
`docker ps -a`. The 104-second gap is the recovery, and no data was lost
because `down` without `-v` never touches the named volume.

**The trap is that the rule protecting the data creates this.** "Git Worktrees"
in `CLAUDE.md` says to pin `COMPOSE_PROJECT_NAME` to the same value the main
tree uses, so a worktree mounts the real volume instead of silently creating an
empty one. That is correct and it must stay. Its consequence is that **every
media worktree is in the same compose project**, so `docker compose down` in
any of them removes the container every other tree and every other app is
using. The project name is what makes the volume shared; it is equally what
makes the container shared.

`media/docker-compose.yml` also pins `container_name: anime_site_postgres_db`,
so the name is global regardless of project — which turns the other direction
of this mistake into a loud "container name already in use" rather than a
second database.

Nothing enforces this. What would:

- **A rule, which costs nothing:** in a tree that shares the project name, stop
  the database with `docker compose stop db`, never `down`. `stop` leaves the
  container to be started again; `down` removes it for everybody.
- **On the box this is worse and the same command does it.** `~/cg1618` runs
  the shared PostgreSQL and the tunnel for all four apps, and a `down` there
  takes production's database out from under every one of them, with nobody
  sitting in front of it. `bin/deploy` does not do this, and no script should
  gain it without a deliberate decision.

Not urgent on a development machine, where the recovery is one `up -d` and the
volume survives. Recorded because the same keystroke on the box has a different
blast radius, and because the reason it is easy to get wrong is a rule this
repository correctly insists on.

## The box's docker daemon still has no default log cap

Every service in `docker-compose.prod.yml` now caps its log driver, and each
app's compose file is expected to do the same for its own service. Neither
covers anything started **outside** a compose file — a one-off `docker run`, a
container the Actions runner leaves behind, whatever a later session starts by
hand while debugging. Those take the daemon default, and the box has no
`/etc/docker/daemon.json` at all, so that default is still `json-file` with no
`max-size`.

It is a much smaller hole than the one that was just closed: the long-lived
containers are all in compose files. What it catches is the container nobody
wrote a compose file for, which is also the one nobody will think to check.

```bash
# on the box, once
sudo tee /etc/docker/daemon.json <<'EOF'
{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "5"}}
EOF
sudo systemctl restart docker
```

**The restart bounces every container on the box**, which is the only reason
this is an open item rather than something already done. It needs a moment
when a few seconds of every hostname 502-ing is acceptable, and it needs root —
the platform sessions reach the box over SSH without passwordless `sudo`, so
this is the owner's to run or to grant.

It does not make the per-service blocks redundant. The daemon default is not
in this repository, where a diff would show it changing.

## `bin/rollback` names a document three apps do not have

Tier 3 freezes and tells the operator:

```
   restoring it is a human's decision; see the app's deploy notes.
```

`media` has them — `deploy/README.md`, plus `docs/deployment-selfhost.md`.
**`travel` and `art` have none**: their `deploy/` holds only the hook, and
neither has a deployment page under `docs/`.

`food` has closed its half — `food/docs/deployment.md`, 107 lines, verified
against what `bin/deploy` and `bin/rollback` actually print rather than written
from memory. **Copy that page rather than starting from this list**, and take
its closing rule with it: *if what the freeze prints and what the page lists
ever disagree, believe the box.* A page describing paths is a second copy of
something the script already knows, and which copy goes stale is the question
this repository spent a day answering.

So at the worst moment the platform produces — production frozen mid-rollback,
a human deciding whether to restore a dump — the script points three of four
apps at a document that does not exist. The pointer was written when `media`
was the only app, and it is still correct for `media`.

**This is due before the first migration release, not after.** `food` and
`travel` are both at `0001_baseline` on the box, so whichever releases first is
the platform's first migration deploy, and tier 3 is reachable from it.

What such a page has to answer, and the content already exists — it was worked
out the hard way while preparing `food`'s release:

- **What rolling back costs, stated as data rather than as a procedure.**
  `bin/rollback` never restores; it reverses schema through the app's own hook.
  For a first migration that creates the tables, downgrading drops them and
  everything in them. The pre-deploy dump is not a gentler path: it predates
  the release, so restoring it discards every write since. **There is no route
  that keeps the data**, and the real choice is roll back and lose it or fix
  forward. A reader who assumes the dump is the safe option — as one session
  did, reasoning plausibly from the true fact that the dump is taken first —
  will reach for it at exactly the wrong moment.
- **Which revision the database is at**, so the downgrade target in a freeze
  message can be recognised rather than trusted.
- **Where the dumps are**, matching what the freeze prints.

This is narrower and more urgent than "three apps have no `docs/` skeleton"
above. That item is about a shape; this is one named file the tooling already
points at.

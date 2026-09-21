# Decisions

Why the platform is shaped the way it is, including alternatives that were
considered and rejected. This file explains the past; every other page under
`docs/` describes the present.

## Polyrepo, with a platform repository as the master

One repository per app, plus `cg1618-apps/platform` holding what is shared:
`apps.yml`, the apex page, the cloudflared ingress, the shared PostgreSQL, the
deploy scripts, the box documentation and the generic `CLAUDE.md`.

A monorepo was the alternative. It was rejected because the apps genuinely do
not share code — they share a box, a database server and a tunnel, all of
which are the platform's — and because one repository would put every app's
CI on every app's pull request. The cost of the polyrepo is that a change
spanning the platform and an app is two pull requests in sequence, which is
paid regularly and is visible in this repository's history.

## The organisation is `cg1618-apps`

An organisation and a user account share one namespace, so the organisation
could not be `cgentle1618` while that username exists, nor `cg1618`, which a
dormant personal account registered in 2025 and has never used.

The organisation is what makes one self-hosted runner and one reusable deploy
workflow serve every repository. That is the reason for it, not tidiness.

## `cg1618` for the project, `cgentle1618` for the person

The same choice was made once already, for the domain: `cgentle1618.com` was
free and considered, and `cg1618` won on length, because the string ends up in
SSH configs, `.env` files and tunnel configuration for years. The argument
applies with more force to repository URLs and directory paths.

## App checkouts nest inside the platform checkout

`~/cg1618/media`, `~/cg1618/food` and so on locally, each its own repository,
each gitignored by the platform. It reads like a monorepo and is not one.

This is what lets a tool opened anywhere in the tree find the platform's
`CLAUDE.md` by walking upward, so the generic rules are loaded for every app
without being copied into each. The cost is that a careless `pytest` or `ruff`
at the platform root walks into the app checkouts, which is why the platform's
own commands name `tests/` explicitly.

## The platform does not run Alembic; it asks the app

The deploy pipeline needs three things from an app's migration tool: the
revision the database is at, what a deploy would add, and a way to reverse.
The platform could have run `alembic` directly, since every app happens to use
it.

It asks through `deploy/migrations` instead, for one reason that is not
hypothetical: **the refusal**. A revision whose author declared it
irreversible must not be downgraded, because reversing it does not restore
what it removed — it invents something in the shape of it, unattended, on the
box, in the minute after a failed deploy. Which revisions are irreversible,
and how that is marked, is the app's knowledge. A platform that ran `alembic
downgrade` itself would have to carry every app's marker convention, and would
get it wrong silently the first time an app chose a different one.

The hook is also read from the **commit being deployed** rather than from the
checkout on the box. Both questions asked before the pull are about the
incoming code, and reading the outgoing copy broke two things: an app's first
deploy, whose checkout predates its own hook, and any fix *to* a hook, which
the run that ships it would otherwise call in its broken form.

## media moved with no git history

`cgentle1618/anime_site` was not transferred or mirrored. `cg1618-apps/media`
starts from a single commit, and the old repository is kept private as the
record.

The old history is four months of a single application's development, much of
it about a deployment that no longer exists, and carrying it would have meant
carrying the box-level parts that now belong to the platform. A branch pushed
from the old checkout did once graft that history in by accident; it was
deleted.

## Exposure is declared in the registry and verified against the internet

`apps.yml` says what an app's exposure should be. Cloudflare Access is
configured in a dashboard this repository cannot see, so the declaration and
the reality were never connected — and `art.cg1618.com` served an
unauthenticated 200 for twenty minutes while the registry called it
`cloudflare-access`, because its DNS record had been created with no Access
application behind it. From everywhere except the open internet, that looks
exactly like a working gate.

`bin/check-exposure` asks the open internet. It is deliberately the opposite
of `bin/health`, which probes from inside the container so that a tunnel
hiccup cannot roll back good code.

## A gated path is defined by the app; the registry declares it and is checked

`docs/registry.md` tells a `public` app to keep its write surface under its own
path prefix and protect that prefix, or a public hostname is a public editor.
Nothing expressed that prefix, and nothing checked it: `exposure` is one enum
for a whole app, and `bin/check-exposure` probes `https://<hostname>` and
nothing below it, so an unprotected write prefix answers ungated at the root —
correctly — and passes.

**The app is the authority.** Which paths an app's writes live on is a fact
about its route table, discoverable only in that repository and changed only by
a commit there. A prefix typed by hand into `apps.yml` is a transcription of
something that lives elsewhere, and it goes stale the moment a route moves,
silently, because the platform has no way to notice. That is the opposite of
`hostname`, `port` and `database`, which the platform *allocates* and the app
receives — those are correctly registry-owned.

So the app ships the definition: one constant that its routers derive their
prefix from and its tests assert against, and a generated `deploy/gated-paths`
committed beside `deploy/migrations`, one path per line, LF. `bin/deploy`
already has that checkout, and reads it from the commit rather than the
working tree for the ordinary reason: the working tree can hold uncommitted
edits, and what ships is what the commit says.

**`deploy/gated-paths` is data, not a hook. It is mode `100644`.** Nothing
execs it, so none of the executable-bit machinery around `deploy/migrations`
applies to it — and that is worth stating because the analogy invites it. A
check asserting `100755` on a data file would fail forever, reporting a
permission problem that does not exist. Assert `100644` and LF, with the same
`git ls-tree HEAD` mechanism the migrations hook is checked by and a different
expected value.

**`apps.yml` still carries `gated_paths`, and a disagreement is a refusal.**
This mirrors `migrations`, which is a declaration rather than a description:
`bin/deploy` refuses in both directions when the registry and the repository
disagree, because which of them is right is a person's call. The same applies
here.

The analogy is not exact, and the difference is the reason the registry holds
the values rather than a boolean. `migrations` is a boolean because `bin/deploy`
only needs to know whether a hook should exist; it has the hook itself to run.
`bin/check-exposure --all` has no app checkout — it runs from this repository
against the open internet, and on a development machine the apps are cloned
here but the registry's `path` describes the box's layout. It therefore needs
the path strings themselves to have anything to probe. Two copies were accepted
deliberately, with the drift made loud at deploy, rather than making the check
runnable only from the box.

Rejected: leaving the registry silent and the policy Cloudflare-side only. It
is cheaper, and it reproduces exactly the gap `bin/check-exposure` was written
to close — a gate asserted in a dashboard this repository cannot see, with
nothing connecting the claim to the reality.

## Apps emit streams; the box aggregates

The question was whether to build a log system per app and integrate them, and
whether production console output should be viewable at all. The answer is no
per-app log system and no bespoke integrated one: **an application's logging
obligation ends at stdout**, and one collector on the box aggregates every
container's stream.

The alternative — each app owning a log viewer, and something later joining
them up — was rejected for the reason the polyrepo was chosen in the first
place. The apps share a box, a database server and a tunnel; those are the
platform's, and so is this. Four log viewers would be four implementations of
one thing, diverging the way four of anything here diverges, and the
integration would still have to be written afterwards against four shapes
instead of one.

It also puts the work where the leverage is. An app's half is a `dictConfig`
and a middleware — hours, once, and then never thought about again. The
platform's half is one collector that gains every app the day it is switched
on, including the two apps nobody is currently working in.

**Loki rather than ELK.** Both are free and self-hostable, and Elasticsearch
would eat a mini PC on its own. Loki indexes labels rather than full text,
which is the right trade for a box where the question is almost always "what
did this container do around this time" rather than "find this word anywhere in
a year". Grafana Alloy tails the docker socket and labels streams by container;
Grafana reads Loki. All three are Grafana Labs OSS — Loki and Grafana AGPLv3,
Alloy Apache 2.0 — with no Grafana Cloud or Enterprise involved.

Resources were the only real objection, and they were measured rather than
estimated before committing: on 2026-09-20 the box had 14.0 GB of 15.2 GB RAM
available and 80 GB of 98 GB disk free, with all seven containers together
under 550 MB. The stack's expected 400-500 MB is about 3.5% of memory. Dozzle
— one container, live tail, stores nothing — was the fallback had the box been
tight, and it is not the same product: it has no history, and history is half
the point. It was not needed.

**Audit trails are explicitly not this.** "Who changed this entry", "Pull All
rewrote 312 rows" — that is domain data about a user's own records, it belongs
in the app's own PostgreSQL and its own UI, and it is queried by a person
asking a question about their data rather than by someone working out why the
box is behaving strangely. Conflating the two produces a log system that is
also a weak database, and an audit trail that disappears on a container
recreate. The contract is in [../logging.md](../logging.md).

## The collector is in the registry; the apex page is not

Both are infrastructure in this repository rather than applications in
`cg1618-apps/<name>`, and they are treated oppositely. The reason is not
tidiness, and "is it an application" turns out to be the wrong question.

**`bin/check-exposure` iterates `apps.yml`.** A hostname that is not in that
file is a hostname nothing probes — and a `cloudflare-access` DNS record with
no Access application behind it looks identical to a working one from
everywhere except the open internet. `art` served unauthenticated for twenty
minutes on exactly that. Grafana holds every application's logs, so it is the
worst hostname on the box to get that wrong about, and being probed is worth
more than the tidiness of keeping non-apps out.

The apex page needs none of that: it is `public`, it authenticates nobody, and
there is nothing for a check to discover. Its rule stands — the day it needs a
backend it becomes `cg1618-apps/landing` with an entry like any other app.

The cost is a schema change: `repo` is now nullable, meaning platform-owned,
and `bin/validate_apps.py` refuses `migrations`, a `database` and a `path`
alongside it rather than ignoring them. The alternatives were worse. Inventing
`cg1618-apps/logs` would have put a repository in the registry that does not
exist, so `bin/provision` would clone nothing and the entry would lie. Emitting
the hostname unconditionally from `bin/generate_ingress.py`, like the apex
rule, would have routed it while leaving it outside the only check that asks
whether the gate is real — which is the whole failure being avoided.

A side effect worth having: `logs` reserves port 8008. `apex` listens on 8007
with no entry, so nothing stops a future app claiming 8007 and colliding with
it.

The consequence to accept is that the apex page now lists `logs`, because that
page renders every entry. It is a public page, so the hostname is public
knowledge. That costs nothing real — every hostname with a Cloudflare
certificate is already in the public Certificate Transparency logs, so hiding
it from the apex page would have hidden it from nobody.

## The development database belongs to the platform

One PostgreSQL on each development machine, holding one database per app, in
`docker-compose.dev-db.yml` **here** rather than in an application's compose
file. Container `cg1618-dev-db`, volume `cg1618_dev_pgdata`.

It began as `anime_site_postgres_db` in **media's** compose project, because
media was the only app. The misleading name is what gets noticed - three apps
started a container named after a fourth, and after the repository was renamed
the name pointed at nothing that existed. **The name was the smaller half.**

The real defect was ownership, and it had already cost a morning. On
2026-09-19 the shared container vanished from a development machine and was
reported as unexplained. `docker events` held the sequence - `kill`, `stop`,
`die`, `destroy` in one second, with the volume unmounted rather than removed,
which is the signature of `docker compose down` rather than a crash. The cause
was that the container belonged to media's project, so a `down` in any media
tree removed the database every other app was using. No data was lost, because
`down` without `-v` does not touch a named volume, and the whole thing read as
data loss for a minute and a half.

A compose project of its own removes the mechanism rather than warning about
it. Nothing an app runs can adopt, recreate or destroy the server, because it
is not in any app's project.

**The trade that was considered and not taken: a container per app.** It would
have answered the same instinct - one app going down should not drag the others
- but that instinct is already satisfied by the move, since apps are isolated
by database and no app's compose can reach the server. What per-app containers
would actually buy is **parallel test runs**: the machine-wide pytest lock
exists only because four apps share one server. What they cost is a port and a
postgres process per app, development diverging from production, and a lock
that must become per-app in the same instant across five repositories - and if
it does not, two sessions take different locks and run pytest concurrently,
which is precisely what the lock prevents. Worth doing on its own merits one
day, not worth smuggling into a move.

**Production was never wrong, and was renamed separately.** `cg1618-db-1` in
`cg1618_pgdata` has always belonged to the platform. Two `anime_site` names
survived this move and were deliberately left to a maintenance window of their
own, which they got on 2026-09-21 - see "The last two `anime_site` names in
production" below.

## The last two `anime_site` names in production

Media's live database was `anime_site_db` and its checkout on the box was
`~/anime_site`, both inherited from the app that existed before the platform
did. On 2026-09-21 they became `media` and `~/media`.

Nothing was wrong with them. They were left alone through the repository
split and the development-database move, each time for the same reason:
renaming a live database is downtime and a dump on the one app anybody
actually uses, and a rename bundled into a change that is really about
something else is how an outage acquires two candidate causes. The argument
for finally doing it is not correctness, it is that the registry's `path` key
existed to describe a single app, and `apps.yml` had to carry a paragraph of
explanation at two separate fields for a reader to understand why one app was
spelled differently from the other three.

**What made it cheap to do deliberately** is that the shape of the platform
had already absorbed most of the blast radius:

- **The compose project was already `media`**, and had been since the split.
  It is pinned in the box's `.env`, not derived from the directory, so moving
  the checkout could not conjure a second volume. That is exactly the trap
  "Git Worktrees" in `CLAUDE.md` describes, and it was already closed.
- **The app's data is in bind mounts** (`static/covers`, `static/library`)
  relative to the compose file, so it moved with the directory rather than
  needing to be copied.
- **The database name reaches the app through `.env` alone.** `ALTER DATABASE
  ... RENAME TO` plus two edited lines was the whole change; no dump and
  restore, because a rename is not a data operation.

**What did not absorb it, and is the part worth remembering:** the five
systemd units are installed copies under `/etc/systemd/system` with the
checkout path written into `ExecStart` absolutely, and `deploy/backup/lib.sh`
defaults `REPO_DIR` to the old path. Renaming the directory does not tell
either of them. Both were updated in the same window; a rename that stopped
at the git checkout would have looked entirely successful and produced its
first failure at 04:00 the following morning, in a backup job nobody was
watching.

## `media` is the reference because it is read, not because it is right

"House style" names `media` the reference implementation the other three copy
conventions from. That is the correct rule and it stays. What it must not be
read as is that `media` is where the truth lives, because on the day it was
written `media` was measurably wrong in places the apps copying it were
right.

Three instances, all from 2026-09-19:

- **Migration naming.** `media` uses mnemonic revision ids throughout.
  `food`, `travel` and `art` each carry `0001_baseline.py` from the same app
  skeleton, so three of four apps agreed and all three were inheriting one
  decision nobody made. Reading the neighbours rather than the reference sent
  `travel` to `0002_packing`, and very nearly sent a correction to `food`,
  which was the only new app actually following `media`.
- **`strictPort`.** `food`, `travel` and `art` all set it. `media` does not.
  The three apps that copied the reference are ahead of it, because they made
  a choice it never revisited.
- **The frontend fetch wrapper.** `media`'s renders an array-shaped Pydantic
  422 as `[object Object]` and discards the status code, which makes its own
  documented 409 contract unusable. `food` did not inherit either, because
  when it asked about the convention it was told to write the fixed wrapper
  rather than copy the shipped one.

**The mechanism that protected `food` was not `media` being correct.** `media`
is still broken on both counts. It was `media` being asked to justify itself
and answering honestly.

So the rule in practice: **read the reference rather than the neighbours,
because the neighbours may all be inheriting one unmade decision — and ask the
reference why, because it may be a starting point that has not been revisited
rather than a decision.** An app that finds the reference wrong and says so is
the rule working, not an app going off-style. What the section rules out is
diverging silently, not diverging.

**Three in one evening is not a base rate, and reading it as one inverts the
rule.** These surfaced together because `food` was asking convention questions
in detail and every answer was verified against the file rather than relayed —
a high-attention night, not a typical one. The conclusion is that the
reference is a starting point which has to defend itself when asked. It is not
that the reference is usually wrong: an app that stops reading `media` because
of this entry has taken exactly the wrong lesson from it, and will reinvent
conventions that were right all along. Ask, and believe the answer when it
holds up.

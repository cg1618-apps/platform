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
already has that checkout and already reads an app-shipped file from the
commit rather than the working tree, because `core.fileMode` is false on the
development machines and the working tree lies about modes.

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

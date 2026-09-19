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
- `schema/apps.schema.json` gains an optional `gated_paths` array of strings.
- `bin/deploy` refuses when the registry's `gated_paths` and the app's
  `deploy/gated-paths` disagree, in both directions, reading the app's file
  from the commit rather than the working tree.
- `bin/check-exposure` probes each declared path for the Access redirect the
  way it already probes the root, and its refusal tests are written against a
  fixture that makes refusal possible.

The registry change is the platform's and must be ready before food's first
write endpoint reaches `main`.

## Three apps have no `docs/` shaped like `media/docs/`

`CLAUDE.md`'s "House style" section requires every feature, rule and behaviour
to be documented as Markdown in that app's `docs/`, shaped like `media/docs/`,
landing in the same commit as the behaviour change. That rule landed in #48 and
is right. It also declares three apps short the moment it was written:

| App | Markdown pages under `docs/` |
| --- | --- |
| `media` | 34 |
| `travel` | 4 (`README.md`, `notes/`, and live `superpowers/` scaffolding) |
| `food` | 2 (`README.md`, `notes/`) |
| `art` | 2 (`README.md`, `notes/`) |

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

Not blocking. Worth knowing before the first migration goes out rather than
during it, and worth doing deliberately — arm an app's environment with
`bin/provision` on a repository that has none, and watch the first gated
deploy rather than discovering it under a release.

Recovered from a working report left by the step-4 deploy-pipeline round,
which was never in git and has been deleted. Its two other unverified claims —
SC2088 on the `bin/` scripts and the workflow parsing under `actionlint` — are
closed: `ci.yml` runs both on every pull request and has been green since.

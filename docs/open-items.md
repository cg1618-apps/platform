# Open items

Known defects and unmade decisions that nobody is currently working on.
Everything here is open by definition: there is no status column and nothing is
claimed. An item is closed by **deleting it in the same change that fixes it**,
and that commit is the record.

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

## The box's hardware watchdog does not reset it

`deploy/host/` is installed and its parts are tested on the box —
`docs/shared-stack.md`, "The box recovers itself", says what each covers. The
exception is the TCO watchdog: loaded, fed, and blocked from resetting the
board by the firmware. Lockups are turned into panics instead, which kdump
recovers, so what is left uncovered is a hang the lockup detector cannot see.
What is still open:

- **Which BIOS setting blocks the watchdog reset**, if a hang the lockup
  settings miss ever happens. Deferred until then; the plug recovers it.
- **A DHCP reservation for the box** on the router above the H3C. A plug
  cycle on 2026-10-08 moved it from one address to another; the tunnel does
  not care, but the LAN route has to be found again each time.
- **The router's log for 18:35 on 2026-10-05**, if it keeps one, is the only
  record of what dropped the link.

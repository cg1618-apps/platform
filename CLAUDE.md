# CLAUDE.md — the cg1618 platform

This file is loaded by every session started in this directory **and in every
application directory below it**, because Claude Code walks the filesystem
upwards rather than stopping at a repository boundary. So it holds the rules
that are true for every repository on this box, whatever it is written in.

An application's own `CLAUDE.md` loads *after* this one and wins any conflict.
Put a rule there when it names a framework, a command, a table or a file that
only that app has; put it here when it would be just as true of an app written
in something else.

## What this repository is

The master repository for the box. It owns `apps.yml` — the registry every
application derives from — the shared PostgreSQL and Cloudflare Tunnel, and, as
the platform sequence proceeds, the deploy pipeline and the apex page. It
connects the applications by configuration, not by git pointers: it knows about
them and does not contain them.

- `docs/registry.md` — what `apps.yml` guarantees, and how an app is added.
- `docs/shared-stack.md` — the PostgreSQL and tunnel every app shares, and the
  contract an app joins them on.
- Each app is cloned **inside** this directory and ignored by it, so the two
  histories never meet. A session working on infrastructure runs from here; a
  session working on one app runs from that app's directory.

## The apps

| App | What it is |
| --- | --- |
| `media` | Media tracker and database — anime, film, television, books, comics, games. The oldest and largest. |
| `food` | Ingredient library, how to pick and preserve them, recipes and general recipes, what is cookable with notes, the cooking schedule, what is in the kitchen now, desserts with health information, a random picker, restaurants. |
| `travel` | Packing and buying lists, rules, transport information, and the current planned trip. The smallest of the four. |
| `art` | Practice records and progress, a stopwatch and timer, what to draw, references, schedule, tool notes, libraries of expressions and accessories, a roadmap, and artists worth following. |

Only `media` exists today. The others are built in the order **`food`,
`travel`, `art`**, and all three are `public`, so none of them needs a
Cloudflare Access policy before it can serve.

**Python and PostgreSQL are the only guaranteed common ground.** Framework,
frontend, migration tool and whether there is a build step at all belong to each
app, and nothing in this file may assume otherwise. That is what the app
contract in `docs/registry.md` exists to keep honest — and `art`'s stopwatch is
the feature most likely to want a different shape from the rest, so it is the
one to decide deliberately rather than by inheritance.

## Verifying a file's mode

**`git ls-files` reads the index. `git ls-tree HEAD` reads the commit.** Only the
second one says what ships.

This matters because `core.fileMode` is false on the development machines, so
the executable bit is never picked up from disk and must be set explicitly with
`git update-index --chmod=+x <path>`. Worse, `git commit -- <pathspec>`
re-diffs the named files against the working tree and can silently reset the
mode it just gained.

That combination has produced the same defect three times in two days — a
deploy script committed non-executable, which fails on the box with `Permission
denied` and nowhere else. Twice the check that was supposed to catch it was
`git ls-files`, which showed `100755` from the index while the commit held
`100644`.

So: set the bit, commit, then verify with

```bash
git ls-tree HEAD -- <path>     # the only check that answers the question
```

An app's CI should also assert it, since a human verifying by hand is the part
that keeps failing.

## Subagents

**Use them by default.** A task that can be described completely in writing and
checked when it comes back should go to a subagent: executing one task of a
plan, a search across several directories, a self-contained implementation, a
review pass. It is faster, and it keeps the main session's context for the
judgement that actually needs it rather than filling it with file dumps.

Dispatch several at once when the tasks are genuinely independent — different
files, no shared state, no ordering between them.

**What stays in the main session:**

- **Anything needing the owner.** A subagent cannot ask a question. If a task
  might turn on a decision only the owner can make, either settle it first or
  tell the agent to stop and report rather than choose.
- **Opening and merging pull requests.** That gate is the owner's, and it is
  not delegable to something that cannot read their reply.
- **Anything depending on this conversation.** A subagent starts blank: it gets
  the prompt and the repository, nothing else. Work that only makes sense given
  the last hour of discussion has to carry that context in the prompt, or it
  has to stay here.

**Review what comes back before dispatching the next one.** The failure mode is
not a subagent doing the wrong thing loudly; it is three of them doing subtly
different things and the differences only showing up two tasks later.

## Two Development Machines (company / home)

Work is developed on two machines — **company** and **home** — and is often
stopped halfway on one and continued on the other.

- **Code travels by git (`origin`). Nothing else does.** `.env`,
  `credentials.json`, `CLAUDE.local.md`, virtual environments, `node_modules`
  and any build output are per-machine and are rebuilt or recreated where they
  are needed.
- **Database contents travel by whatever channel that app defines**, and each
  app documents its own. The media tracker's is a Google Sheet, written by an
  admin action and read back by another; an app with no such channel moves data
  by dump and restore, or not at all.
- **`CLAUDE.local.md` says which machine you are on.** It is gitignored, each
  machine has its own, and each names itself — so read it rather than inferring
  the machine from a path or from memory. Never copy one machine's to the other,
  and never commit it.
- **The box is not one of the two machines**, and never participates in a
  handover. It is production: it takes code from `main` and data from its own
  dumps.

**Before switching away**: push your commits, write any half-done state into
`docs/` — the next session starts blank, and the branch name is the first thing
it cannot guess — and run whatever backup that app defines if data changed.

**After switching in**: `git fetch origin` and check out the branch you left
work on (a bare `git pull` silently leaves you on the wrong branch with the
right-looking history); start the app's database; install dependencies if they
moved; run migrations before restoring any data; then build whatever the app
serves from a build directory.

**The company machine has not been migrated to this layout.** It still holds a
clone of the archived `cgentle1618/anime_site`, and migrating it is a fresh
clone alongside rather than a replacement. The media tracker's
`docs/switching-environments.md` holds the procedure and the per-machine
detail; read it from the machine rather than from memory.

## Git Worktrees

**`git checkout` is the default; a worktree is the exception.** Switching
branches in place is instant, carries uncommitted work with it, and costs at
most one rebuild. A worktree costs a full per-machine setup that it inherits
none of, so it has to earn that. Exactly two things earn it:

1. **More than one session or task at once.** One checkout has one `HEAD`, so a
   second branch needs a second tree — see "Concurrent Claude Code Sessions".
2. **Two versions running side by side**, to compare behaviour or to keep a
   stable instance up while something is broken.

**Nothing has to be declared in advance.** A worktree can be added at any
moment and does not touch the existing checkout, uncommitted changes included:

```bash
# from the main directory, mid-task, whatever branch is checked out
git worktree add ../<repo>_<topic> -b <type>/<topic> dev
```

`dev` at the end matters — branch off `dev`, not off whatever the main
directory happens to be on. So **the first task keeps the main directory and
each additional concurrent task takes a worktree**, which puts the setup cost on
the rarer case. Remove it with `git worktree remove ../<repo>_<topic>` when the
branch has merged.

**Where an app ships a worktree helper, use it rather than doing the setup by
hand** — the media tracker's is `.\worktree.ps1 -Topic <topic>`. A script step
cannot be skipped the way a checklist item can, and one of the gaps below
destroys nothing yet looks exactly like data loss.

What such a setup has to cover, whatever the app:

- **Pin the compose project.** Compose derives the project name from the
  directory and **prefixes volume names with it**, so a worktree silently mounts
  a brand-new EMPTY database on the same port while the real data sits untouched
  in the original volume — and the app cheerfully creates a schema and seeds a
  fresh admin in it. Set `COMPOSE_PROJECT_NAME` explicitly in the worktree's
  `.env`, to the same value the main tree uses. This is the single most
  expensive thing to get wrong here, because it reads as data loss and is not.
- **Copy the per-machine files in** (`.env`, any credentials file) and **rebuild
  anything that records absolute paths** — a virtual environment cannot be
  copied, and `node_modules` needs its own install.
- **Give the worktree its own database.** Every tree on a machine points at one
  PostgreSQL, and what actually collides is **migrations**: a migration run in
  one tree leaves the other tree's code disagreeing with the schema, which is a
  broken app rather than a merge conflict and says nothing about why.
- **One test run at a time across every tree**, whatever the databases — see the
  lock in "Coordinated multi-session runs".
- **Only one tree can hold the ports.** A tree that only runs tests and builds
  needs nothing; one that has to *run* needs its ports moved, and the app's dev
  script should refuse to start rather than fail to bind and surface only as
  proxy errors.

## Git Branches

**Never work directly on `main` or `dev`.** Every task gets its own branch — a
one-line doc fix as much as a subsystem. The branch is what makes the work
reviewable and what makes abandoning it free, and a task that looked
one-line when it was described is exactly the one that grows.

- **Start of every task**, before the first edit:

  ```bash
  git checkout dev && git pull origin dev && git checkout -b <type>/<short-topic>
  ```

  If you have already started editing on `dev`, `git checkout -b` carries the
  uncommitted changes onto the new branch — do that rather than trying to undo.
- **Check who else is in this directory BEFORE you run that.** `HEAD` belongs
  to the working tree, not to you, so that `checkout -b` moves the branch under
  every other session here, mid-edit, and tells none of them. **A clean `git
  status` does not mean you are alone** — that is exactly what I checked on
  2026-09-12 before taking the checkout out from under `anime-site-54`, whose
  next commit then landed on my branch. They were mid-task with their work
  committed; there was nothing in the tree to see.

  What actually answers the question:

  ```bash
  git reflog -8          # HEAD moves you did not make = someone else is here
  git worktree list      # who has already moved out
  ```

  Unfamiliar entries in either mean **take a worktree instead** (below). So do
  uncommitted files you do not recognise. A worktree costs a setup; getting
  this wrong costs someone else their commit, and they find out afterwards.
- **The database does not follow the branch.** Files switch instantly;
  the migration version table does not. Leaving a branch whose migrations you
  have run
  leaves the local database *ahead* of the code you switched to, and the app
  then fails on a column the models still declare — not corruption, but it
  reads like it. Downgrade to the revision the arriving branch expects before
  switching away, or upgrade after switching in. This is the real cost of
  moving between branches here; the files are free.

  **In a shared directory this is not your problem alone.** Every tree on this
  machine points at one PostgreSQL, so running a migration leaves the database
  ahead of *every other session's* code, not just your own next checkout. On
  2026-09-12 an `upgrade head` run to verify a column rename broke entry
  loading for whoever was on `feat/anilist-api` — a live app failing on a
  column its models still declare, with nothing on screen to say a neighbouring
  branch caused it. **Downgrade before you leave a branch whose migration you
  ran**, and if you are the one seeing `column <x> does not exist`, suspect an
  unmerged migration on somebody else's branch before you suspect the data.
- **A branch carrying a migration needs its migration tool's heads checked
  before it merges — a clean git merge proves nothing about it.** Two
  migrations that never touch the same file still collide, because both name
  the same parent revision. Two children of one revision is two heads, and a
  migration tool refuses to run with more than one.

  **Nothing warns you.** The files do not overlap, so git merges them cleanly,
  GitHub reports no conflict, and `git merge-tree` says clean. Merging `dev`
  into your branch does not fix it either — the merge has nothing to resolve.
  The collision lives in the revision graph, which only the migration tool can
  see. Run its heads command after rebasing or merging `dev` in, whenever your
  branch adds a revision and another branch has landed since you branched.

  **Fix by reparenting, not renumbering**: point the new revision's parent at
  the new head. The revision *id* may already be applied to a database, and
  changing it strands that row in the version table.

  Two variants the heads command does not catch. A **stale parent written in
  prose** — a spec or plan naming the head it was drafted against — is
  invisible to a tool that reads revision files, and the two heads appear later,
  when somebody executes the plan as written; so re-check a plan's revision id
  at the moment you execute it, not when you wrote it. And **heads plus an
  incremental upgrade is not proof the chain builds**, because both run against
  a database that already holds the earlier revisions. The from-zero proof is a
  test that runs the real command against a scratch database. Say which of the
  two you actually ran; the weaker claim is worth stating honestly rather than
  rounding up.

  Each app names its own tool and commands in its own `CLAUDE.md`. The media
  tracker's are Alembic's, and its file carries the full version along with the
  incidents that produced it.

- **Name it `<type>/<short-topic>`**, with the same prefixes the commits use:
  `feat/`, `fix/`, `docs/`, `refactor/`, `test/`, `chore/`. `feat/role-locks`,
  `fix/guest-pipeline-409`, `docs/git-workflow`. The branch and its commits
  should agree about what kind of change this is.
- **`main` is production.** It moves only by a PR merged from `dev`. Nothing
  else reaches it, ever.
- **`dev` is the integration branch, and it is not written to by hand either.**
  A feature branch reaches it by PR, so this repository's checks run on the
  work *before* it lands rather than after. A branch merged locally into `dev` gets none of
  that, which is the whole reason the PR is the gate.
- **Everything up to and including a merge into `dev` needs no approval** —
  creating the branch, committing, pushing, opening the PR and merging it. CI
  runs on that PR, so the work is checked before it lands, and `dev` reaches
  production only through a release PR. Nothing that lands there is something
  I have to live with.
- **A PR into `main` is mine** — show me the title and body and wait. That is
  the release, it is the only thing that deploys, and it is where the gate now
  sits. Committing directly to `dev` or `main` is still forbidden outright.
- **After a merge, two words say what happens next, and they are not
  interchangeable.** Both mean the merge succeeded; they differ in whether the
  branch is finished with. I say them on a release; on a `dev` PR you merged
  yourself, make the same call unprompted — tear the branch down unless the
  work continues:
  - **"merged"** — the PR landed, *and there is more to do on this work*. Stay
    where you are: keep the branch, its worktree and its database. Pull `dev`
    if you need the merge, but do not delete anything and do not treat the
    task as closed.
  - **"done"** — the PR landed and the branch is finished with, whichever
    branch the PR went into. Tear it down without being asked:

    ```bash
    git checkout dev && git pull origin dev
    git branch -d <branch> && git push origin --delete <branch>
    git worktree remove ../<repo>_<topic>              # if it had one
    # and drop the scratch database that worktree was given, if it had one
    ```

    **The database goes with the branch.** A worktree gets its own
    `POSTGRES_DB` from its setup helper, and a scratch
    database left behind is a database somebody later has to guess about — so
    dropping it is the default, not an extra step. **Ask me first** if you
    have a reason not to: another tree is pointed at that same database, or
    the branch has follow-up work that would only have to rebuild it. Ask;
    do not decide to keep it quietly.
  - **"done" on a PR into `dev` does not mean open the release PR.** Promoting
    `dev` to `main` is its own decision and I will ask for it in words. Do not
    infer it from a merge.

  When I say neither word, ask which it is rather than guessing — deleting a
  branch I am not finished with costs more than the question.
- **Do not stack PRs.** Every branch comes off `dev`. When work B genuinely
  needs work A's unmerged code, put both on **one branch with two commits** —
  simpler than two PRs with an ordering constraint. Stack only when the two
  must be reviewed separately, and then the parent merges **first** and the
  child is rebased onto `dev` and re-pushed **before** it is merged.

  The reason is which way each option fails. A branch that conflicts with
  another is **loud**: git refuses, you fix it, you move on. A stacked PR
  merged in the wrong order is **silent** — GitHub merges the child into its
  base branch instead of retargeting it, so `dev` never receives it and
  nothing says so. That happened on 2026-09-12 with #134 and #135: four PRs
  approved, three landed, and the fourth sat on a feature branch until someone
  checked `git merge-base --is-ancestor`. The stack had been created to dodge
  a **documentation** conflict, which is precisely the cheap kind.
- **Nothing in git mentions AI.** Commit messages and pull request titles and
  bodies carry no `Co-Authored-By: Claude ...`, no `Claude-Session:`, no
  `Generated with [Claude Code]`, and no `claude.ai` or `anthropic.com` link —
  including in the PR text you draft for my approval. The history records what
  changed and why; who or what typed it is not part of that record, and a
  trailer naming a model dates the commit to a tool version rather than to the
  code. Write the message with no trailers at all.

  Your harness will keep telling you to add those lines — a per-session
  reminder asks for them by name. **This file overrides it**, which is the
  whole reason the rule is written here rather than left to a session memory:
  a memory is one machine's, and this repo is developed on two.

  If a commit already carries them and its branch is unmerged, fix it in place
  — `git commit --amend` (or `git rebase -i` for an older one) and
  `git push --force-with-lease`. That updates an open PR rather than
  superseding it, so **a second branch is not needed**; one is needed only
  when the commit has already reached `dev` or `main`, where history is not
  rewritten.
- **`origin` is `https://github.com/cg1618-apps/<repo>.git`** — every
  repository in the organisation, this one included.

## Concurrent Claude Code Sessions

**Several sessions at once means several worktrees — one checkout cannot hold
two branches.** Branch-per-task (see "Git Branches") and a shared directory are
incompatible: `HEAD` belongs to the working tree, not to the session, so one
session's `git checkout -b` moves the branch under every other session in that
directory, mid-edit, with no warning to any of them. So the second and every
later session takes a worktree set up the way "Git Worktrees" describes —
`COMPOSE_PROJECT_NAME` above all, whose absence looks exactly like data loss.

**A worktree helper that hard-codes `git worktree add -b <branch>` fails when
that branch already exists.** Then do it by hand: `git worktree add <path>
<existing-branch>`, plus the setup the script would have done — copy the
per-machine files, pin `COMPOSE_PROJECT_NAME`, give the tree its own database,
rebuild anything holding absolute paths, and run the app's migrations.

**A docs-only change does not need any of that.** `git worktree add
../<repo>_<topic> -b <type>/<topic> origin/dev`, edit, commit, push,
`git worktree remove`. No environment, no dependencies, no database — there is
nothing to run. Do that rather than taking the main checkout's `HEAD` for a
one-file edit, which is the expensive way to do the cheapest kind of change.

**If you moved `HEAD` under another session and their commit landed on your
branch**, this is the recovery, and it is the one that was actually performed
on 2026-09-12 rather than a sketch of one:

1. Get their commit onto their branch **through a temporary worktree** —
   `git worktree add`, `git cherry-pick`, remove. **Do not `git checkout`**:
   that drags whatever is uncommitted in the shared tree onto another branch,
   under whoever owns it.
2. `git reset --mixed HEAD~1` to take the commit back off the branch it landed
   on. Mixed, not hard: it leaves every working-tree file untouched, which is
   what makes it safe when the files are not yours. Check `git status` first —
   if anything is *staged*, it belongs to someone and a reset unstages it.
3. Prove the base with `git reflog` rather than assuming it. Three entries —
   `branch: Created from HEAD`, the stray `commit:`, the `reset:` — say the
   branch has never pointed anywhere else.
4. **Tell the other session**, with the reflog. They cannot see any of this
   from their side, and their next `git log` will be missing a commit they
   know they wrote.

**Everything below is the record of what happened when that was not the
rule**, on 2026-09-11, when several sessions shared one directory and one
branch. It is kept because the failures it describes are the ones that repeat
whenever two agents touch one working tree — and because a worktree per
session is a rule, not a guarantee. Read it whenever the working tree holds
changes you do not recognise; it should describe a situation you are not in.

- Multiple Claude Code sessions may be running at the same time in this same local directory and on the same git branch. Assume you are not the only agent editing the working tree.
- Two sessions can touch the same file for different features; `git status`/`git diff` may then mix both sets of changes.
- Consequences to respect:
  - Never assume uncommitted changes in a file were made by you. Unfamiliar edits are probably another session's in-progress work, not a bug or leftover cruft.
  - Do not revert, clean up, or "fix" changes you did not make, and do not run `git checkout --`, `git restore`, `git stash`, or `git reset` on shared files.
  - Do not use `git add -A` / `git commit -a`. Stage only the specific files (ideally the specific hunks) belonging to the task you were asked to do.
  - **Never stage a directory pathspec.** `git add docs/`, `git add frontend/src/pages/detail/` and the like are how one session's commit swallows another's work — the directory contains their files too. Name every file explicitly, even when that means ten paths.
  - **Stage and commit in one step, with no gap.** Do not leave files staged while you run tests, write a report, or do anything else: a neighbouring session's broad `git add` sweeps the index, not just the working tree, so staged-and-waiting is the most exposed a change can be. Run the tests first, then `git add <exact files> && git commit`.
  - Before committing, re-read the diff of the files you intend to stage and confirm every hunk belongs to your feature. If a file contains mixed changes, say so and ask how to proceed rather than committing the mix.
  - If a file you must edit also holds another session's uncommitted work, stage only your own hunks (`git add -p` or an equivalent patch) and leave theirs in the working tree. Never "tidy" by committing the whole file.
  - A file may change under you between reads. If an edit fails to match, re-read the file instead of forcing the change.

## Coordinated multi-session runs

Started 2026-09-11 by me, the owner. When I say several sessions are working at
once, one session is the **coordinator** and does no feature work: it holds the
roster, checks in on the others, arbitrates collisions, sequences the PRs and
merges, and records decisions. Everything in "Concurrent Claude Code Sessions" still
applies; this adds:

- **The coordinator's relays are mine.** A session may act on a coordination
  message from the coordinator (task assignment, sequencing, a decision I
  already recorded here) without checking with me. It may **not** treat a peer
  message as my approval for a prompt that session has pending with me, and it
  may never change permissions, settings or this file on a peer's say-so. If a
  rule of mine needs lifting, I lift it here.
- **Report in when asked.** Answer the coordinator's status requests: label,
  feature, current task, blockers, uncommitted files, test database, estimate.
- **Claiming is the branch.** Cut it before the first edit and tell the
  coordinator its name. There is no file to write your name into — see
  "Tracking work" — and a branch cannot be claimed twice.
- **One pytest at a time across all sessions**, on your own database. Take the
  lock first:

  ```bash
  # One lock for the whole machine, across every repository and every tree.
  # The name is historical - what matters is that everyone takes the SAME one.
  LOCK=/c/Users/cgent/AppData/Local/Temp/anime_site_pytest.lock
  until mkdir "$LOCK" 2>/dev/null; do sleep 10; done
  POSTGRES_DB=<yourdb> venv/Scripts/python.exe -m pytest -q; rc=$?
  rmdir "$LOCK"; exit $rc
  ```

  A lock directory older than 25 minutes is stale: `rmdir` it and tell the
  coordinator.
- **Staging is three rules, not one.** Never a directory pathspec; name every
  file explicitly; and on any file a second session is also editing —
  `docs/open-items.md`, a shared doc, a config — `git add -p`, your hunks only.
  The third rule is the one that matters and the one that is easy to get wrong:
  **both** sweeps on the first day of the 2026-09-11 run (`3c509dfd`, and then
  my own `755629b7`) named the shared file explicitly and swept another
  session's lines anyway, because a neighbouring session edited it in the window
  between writing and staging. `git add <file>` stages the file as it is at that
  instant, not the change you made to it. Naming the file narrows nothing on a
  file somebody else is also writing; only `-p` does.

  Retiring the progress file removed the worst instance of this, not the
  hazard — any doc two sessions touch behaves the same way.
- **`git commit` with no pathspec commits the whole index — including what
  another session staged.** This is the fourth rule and the one that defeats
  the other three: careful per-hunk staging protects nothing if the next
  session's bare `git commit` sweeps the index it left behind. It is how
  `80e3a77f` swallowed `cards-link-session`'s hunks minutes after that session
  had staged them correctly, and it happens most easily when a session's own
  commit is **denied** — the denial leaves their blob sitting in the index for
  whoever commits next. So: **always `git commit -- <exact paths>`**, which
  commits those paths and leaves the rest of the index alone. Never a bare
  `git commit` or `-a` on this repo while other sessions are live.
- **The index is shared state, like the working tree.** `git status` before you
  commit, and read what is *staged*, not just what you changed — **including
  the index you inherited.** Rule 4 was written between two sweeps of the same
  session's roadmap entry and did not prevent the second, because the exposure
  was created before the rule existed and nobody went back to look at what was
  already sitting there. A new rule protects new work; it does nothing about a
  blob staged an hour ago by someone whose commit was denied. If your own
  commit is refused, `git reset` rather than leaving the index loaded.
- **Untracked files belong to somebody.** A spec or plan that is not yet
  committed is the most exposed thing in the tree, because a directory
  pathspec picks it up and its author loses the commit message. Check `git
  status --short` for `??` lines that are not yours before you stage anything.

## Tracking work

**There is no progress file, and you do not create one.** Status tracking lives
where git already keeps it: the **branch** says what is being worked on, the
**pull request** says what is proposed, and the **commits** say what shipped.
A status document duplicates all three, goes stale between them, and becomes a
file several sessions write to at once — which is how one session's commit
swallows another's lines. `docs/PROGRESS.md` existed and was removed for exactly
those reasons; do not reintroduce it under another name.

So:

- **Do not** open a task table, a status file, a checklist doc, or a work log.
- **Do not** report status by editing a doc. Report it in the commit message,
  the pull request body, or to the owner directly.
- **Do not** record which session is doing what. A branch has one owner by
  construction, and concurrent sessions each take their own worktree.

Two things a branch cannot hold, and the only two that go in `docs/`:

- **`docs/open-items.md`** — known defects and unmade decisions that nobody is
  currently working on. Everything in it is open by definition: no status
  column, no claiming, no `todo`/`wip`/`done`. An item is closed by **deleting
  it in the same change that fixes it**, and the commit is the record.
- **`docs/switching-environments.md`** — machine state that is not derivable
  from the code: which database is at which revision, where the recovery dumps
  are. Read it from the machine, not from memory, when you update it.

Neither is a work log. If you find yourself writing a date, a session label, or
a sentence in the past tense into either, it belongs in the commit message
instead.

**Finishing a plan is two edits, not one.** Do both in the same commit, without
being asked — this is the step that has needed chasing every time:

1. **Move what is worth keeping out of the spec and plan**, into the ordinary
   docs: design rationales and rejected alternatives into
   `docs/notes/decisions.md`, present-tense behaviour into the matching `docs/`
   page, operational procedure next to the thing it operates. Write it **as it
   ended up, not as it was designed** — development rarely follows a spec
   exactly, and where the two diverged, only what is true now belongs.
2. **Delete the spec and the plan.** Documents under `docs/superpowers/` are
   working scaffolding, not deliverables, and none of them outlives its task.

   The reason is what an abandoned spec does to the next design pass. It
   describes the system as it was *imagined*, in exactly the same confident
   tone as a page that is accurate, and nothing on its face says which it is.
   Phase D's spec argued it had to come last because "until this ships, modes
   can only be changed in the database" — the ordering was right and the reason
   was incomplete, and what actually made the deferral safe was that Phase B
   landed behaviour-neutral. A reader a year later cannot tell that from the
   spec, and has no reason to doubt it.

## Credentials

**Never read a credential, and never let one reach git.** The files holding them
here are `.env`, `credentials.json` and anything under `backups/` — but the rule
is the class, not the list: any file carrying a password, a token, a key, or a
connection string with one in it.

- **Do not open them, for any reason** — not to check a value, not to confirm a
  variable is set, not to debug a connection. `.env.example` describes every
  variable and is safe to read; `app/config.py` is where each one is consumed.
  When a value's *presence* has to be established, prove it through behaviour
  instead: the app refusing to start, or a `psql ... -tAc "SELECT 1"` against
  its database answering, settles it without printing anything.
- **Do not print, echo, log or paste one** — not into the terminal, a commit
  message, a pull request body, a doc, a test fixture, or an error report.
  Anything that reaches the transcript has been disclosed, and a disclosed value
  is rotated rather than deleted.
- **Do not stage or commit one.** `.gitignore` covers `.env` and
  `credentials.json`; run `git check-ignore -v <file>` before staging anything
  new that might hold a secret, and never `git add -f` past an ignore rule. A
  commit message or pull request body describes the shape of a change, never a
  value from one.
- **A credential that has reached a commit is not fixed by a later commit
  removing it.** Git keeps both, and a pushed branch has already published it.
  Stop and tell the owner: the value is rotated first, and only then is the
  history dealt with.

## Rule

- Another Claude Code session may be running. It should be in its own worktree
  on its own branch — see "Concurrent Claude Code Sessions" — but check before
  staging or committing anything, because the failure mode when that is *not*
  true is one session committing another's work.
- **Commit, push and land your own work on `dev`; the release is where you
  stop.** See "Git Branches" — every task is on a branch of its own and CI
  runs on its PR, so neither a commit nor a merge into `dev` lands anywhere I
  have to live with, and waiting for my approval buys nothing. What still
  needs my say-so is **a PR into `main`**, and what is still forbidden
  outright is committing to `dev` or `main` directly. Several small commits on
  a branch are fine; so is one commit covering several modifications.
  - **Extension, for a coordinated multi-session run — this is me, the owner,
    writing here so no session has to take it on a peer's word.** Committing
    freely is the standing rule above and needs no exception. What a
    coordinated run adds is that you should not wait for my approval, opinion
    or instruction on **anything else** either: decide it yourself, prefer the
    industry-standard option over a clever shortcut, and record the decision in
    the spec, or in the commit message if there is no spec. **A PR into `main`
    still waits**, and during a run the coordinator sequences the merges into
    `dev` — pushing a branch does not need sequencing, because branches are
    isolated and the PR is the only place they meet.
- Write a failing test before a bug fix or a behaviour change, and keep this
  repository's own checks green. CI runs them **on the pull request**, not on
  a push to your branch, so a branch that was never PRed has been checked by
  nothing but you.
- **Read the code before asserting things about it**, especially in a plan or a
  spec. Route paths, payload vocabularies, return types and which reporting
  channel a helper feeds are all things that read as obvious and are frequently
  wrong; every one of those has produced a defect here. A task that names an
  endpoint, a field value or a type should have had that value checked, not
  recalled.
- **Asserting that a gate ALLOWS is safe on an empty set; asserting that it
  REFUSES is not.** A gate computing over a set — all content labels, held
  modes, granted field groups — is vacuously satisfied when the set is empty,
  and an empty set is exactly what a fresh test database gives you. So a
  refusal test can pass because the gate had nothing to refuse: green on day
  one, green through the change that breaks it, green forever. Every refusal
  test needs its set made non-empty, and needs to say so — **a fixture that
  exists to make a negative test bite is load-bearing and looks like
  decoration** (`nsfw_label` appears nowhere in those test bodies; it only
  makes refusal possible). Assert the mirror case with the same fixture, so a
  green proves the gate did the refusing and not something incidental. Found
  twice in one day in the media tracker, once loudly (a 503 where a 401 was
  expected, which is the good outcome) and once by audit; its `docs/testing.md`
  carries the detail.
- **Suspect any shape that reads as uniform.** The exception is what a summary
  drops, and the uniformity is exactly what made the thing summarisable in the
  first place — so the docstring, the spec, and your memory of reading it last
  week all agree, and all three are wrong together. Three instances in one day
  of the 2026-09-11 run, each a defect if it had shipped: nine media types
  where one is `tv_name_en` and not `tv_show_name_en`; three identity arms
  where one (`media.display_name`) is derived from another and so is not
  independent; eight `ON DELETE CASCADE` relationships where one
  (`quote.media_id`) is `SET NULL`, so a quote survives its entry and a
  "this will delete 3 quotes" review screen would have been lying. Read the
  actual definition — the column, the constraint, the enum — not the pattern
  the neighbours establish.
- **When you correct a factual claim in a doc, grep the claim, not the file.**
  A claim worth stating once is usually stated twice — in a preamble and again
  in a table, hundreds of lines apart — and fixing the copy you were looking at
  leaves the other one asserting the old thing with equal confidence.
  The media tracker's `data-actions.md` said its data-control router was gated
  by one dependency in two places; the second was found by accident, while
  editing that table for an unrelated reason. Same failure as the uniform-shape
  one above: a second copy of something that reads as settled.


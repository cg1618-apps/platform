# Step 2: the `cg1618-apps/platform` repository — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `cg1618-apps/platform` holding `apps.yml` and the machinery that
keeps it honest — a JSON Schema, a policy validator, a `Tests` workflow and a
branch ruleset that makes the check required — without moving anything off the
media tracker or touching production.

**Architecture:** The repository is the registry and nothing else yet. `apps.yml`
declares each application's hostname, port, database, exposure and health path;
a schema checks its shape and a validator checks the policy a schema cannot
express. Both run in CI on `ubuntu-latest`, never on the self-hosted runner. The
generators that consume `apps.yml` — the cloudflared ingress, the apex
navigation — are deliberately **not** built here; they arrive with the steps
that move the files they generate.

**Tech Stack:** Python 3.13 (stdlib plus `PyYAML` and `jsonschema`), pytest,
GitHub Actions, `actionlint`, `shellcheck`, GitHub rulesets.

**Spec:** `docs/superpowers/specs/2026-09-17-cg1618-platform-architecture-design.md`
— copied into this repository by Task 2, because its only other copy is in the
archived `cgentle1618/anime_site`, on a branch that never merged.

## Global Constraints

- The organisation is **`cg1618-apps`** and every repository in it is **public**.
  Rulesets and environments with required reviewers are free only for public
  repositories, and both gates depend on that.
- **No `pull_request`-triggered job may ever run on the self-hosted runner**, in
  any repository. Everything in this plan runs on `ubuntu-latest`.
- **`dev` is the default branch**; `main` is production and moves only by a
  release pull request. Never commit directly to either.
- **Nothing in git mentions AI** — no `Co-Authored-By`, no generation trailer, in
  any commit message or pull request body.
- **`gh` needs `admin:org` on each machine separately** (`gh auth refresh -h
  github.com -s admin:org`). The home machine already has it.
- Some GitHub calls in this plan may be refused by the harness's auto mode
  (creating a repository, editing a ruleset). Every such step below carries its
  browser equivalent; hand it to the owner rather than working around it.
- **`Documents\cg1618\` already contains `media\`**, so it cannot be cloned
  into. Task 2 initialises the repository in place.

---

### Task 1: Create the repository and its default branches

**Files:** none locally — this task is entirely GitHub-side.

**Interfaces:**
- Consumes: the `cg1618-apps` organisation.
- Produces: `cg1618-apps/platform`, public, with `dev` as the default branch and
  an initial commit on both `dev` and `main`.

- [ ] **Step 1: Create it**

```bash
gh repo create cg1618-apps/platform --public \
  --description "The cg1618 platform: apps.yml, shared infrastructure, deploy pipeline."
```

Browser equivalent if auto mode refuses: https://github.com/organizations/cg1618-apps/repositories/new
— owner `cg1618-apps`, name `platform`, **Public**, no README, no .gitignore, no
licence. The repository must be created **empty**; Task 2 writes the first
commit.

- [ ] **Step 2: Confirm it is empty and public**

```bash
gh api repos/cg1618-apps/platform --jq '{private, default_branch, size}'
```

Expected: `"private": false` and `"size": 0`. A non-zero size means an
auto-generated README landed; delete the repository and recreate it empty rather
than working around it, because Task 2's first commit is what defines the tree.

---

### Task 2: Initialise the working tree in place and push the first commit

`Documents\cg1618\` holds `media\` already. Cloning into it is impossible, so
the repository is initialised where it stands and `media\` is ignored.

**Files:**
- Create: `C:\Users\cgent\Documents\cg1618\.gitignore`
- Create: `C:\Users\cgent\Documents\cg1618\README.md`
- Create: `C:\Users\cgent\Documents\cg1618\docs\superpowers\specs\2026-09-17-cg1618-platform-architecture-design.md`
- Create: `C:\Users\cgent\Documents\cg1618\docs\superpowers\plans\2026-09-18-step-2-platform-repo.md`

**Interfaces:**
- Consumes: the empty repository from Task 1.
- Produces: `dev` and `main` both pointing at the initial commit; a working tree
  at `Documents\cg1618\` whose `git status` does not see `media\`.

- [ ] **Step 1: Initialise and point at the remote**

```bash
cd /c/Users/cgent/Documents/cg1618
git init -b dev
git remote add origin https://github.com/cg1618-apps/platform.git
```

- [ ] **Step 2: Write `.gitignore` before anything else**

This comes first because `git status` in this directory otherwise offers to
commit the entire media tracker, `node_modules` and `venv` included.

```gitignore
# Each app is its own repository, cloned inside this one. The two histories
# never see each other, which is what makes the nesting safe.
/media/
/art/
/food/
/journal/
/health/
/money/
/travel/

# Per-machine, never committed.
CLAUDE.local.md
.env
credentials.json

__pycache__/
*.pyc
.venv/
venv/
```

- [ ] **Step 3: Verify the ignore actually hides the app**

```bash
cd /c/Users/cgent/Documents/cg1618
git status --short
git check-ignore -v media/CLAUDE.md
```

Expected: `git status` lists only the files this task creates — **no `media/`
entry at all** — and `check-ignore` names the `/media/` rule. If `media/` still
appears, stop: committing it would put a second copy of the media tracker in the
platform repository.

- [ ] **Step 4: Write `README.md`**

```markdown
# cg1618 platform

The master repository for the cg1618 box. It owns `apps.yml` — the registry
every application is derived from — and, as later steps move them, the shared
PostgreSQL, the Cloudflare Tunnel ingress, the backup units and the deploy
pipeline.

It connects the applications by configuration, not by git pointers: it knows
about them and does not contain them. Each app is cloned inside this directory
and ignored by it, so the histories never meet.

- `apps.yml` — one entry per application; everything else derives from it.
- `schema/apps.schema.json` — the shape `apps.yml` must have.
- `bin/validate_apps.py` — the policy a schema cannot express.
- `docs/` — how the box is arranged and why.

`main` is production and moves only by a release pull request from `dev`.
```

- [ ] **Step 5: Bring the spec and this plan across**

The spec's only other copy is on an unmerged branch of an archived, private
repository. It argues for steps 3 and 4 as well as this one, so it travels here.

```bash
mkdir -p docs/superpowers/specs docs/superpowers/plans
cp /c/Users/cgent/Documents/anime_site/docs/superpowers/specs/2026-09-17-cg1618-platform-architecture-design.md \
   docs/superpowers/specs/
cp /c/Users/cgent/AppData/Local/Temp/claude/C--Users-cgent-Documents-anime-site/9013ac59-466c-4b4b-bef2-65020b7e359e/scratchpad/2026-09-18-step-2-platform-repo.md \
   docs/superpowers/plans/
```

- [ ] **Step 6: Commit and push both branches**

```bash
git add .gitignore README.md docs/superpowers/specs/2026-09-17-cg1618-platform-architecture-design.md docs/superpowers/plans/2026-09-18-step-2-platform-repo.md
git commit -m "chore: the platform repository, with the spec it is built from"
git push -u origin dev
git push origin dev:main
```

`dev` and `main` start identical, so the first release pull request has a base
to compare against.

- [ ] **Step 7: Make `dev` the default branch**

```bash
gh api -X PATCH repos/cg1618-apps/platform -f default_branch=dev --jq '.default_branch'
```

Expected: `dev`. Browser equivalent: Settings → General → Default branch.

---

### Task 3: `apps.yml` and its schema

**Files:**
- Create: `apps.yml`
- Create: `schema/apps.schema.json`
- Create: `tests/test_apps_schema.py`
- Create: `requirements-dev.txt`

**Interfaces:**
- Consumes: the repository from Task 2.
- Produces: `apps.yml` at the repository root, validated against
  `schema/apps.schema.json` by `tests/test_apps_schema.py`. Task 4's validator
  reads the same file with `yaml.safe_load` and expects a top-level `apps` key
  holding a list of objects.

- [ ] **Step 1: Write `requirements-dev.txt`**

```
PyYAML==6.0.2
jsonschema==4.23.0
pytest==8.3.4
```

- [ ] **Step 2: Write `apps.yml` with the one application that exists**

The other six are planned, not built. They enter this file when they are
provisioned — an entry here is a claim that a hostname, a port and a database
are taken, and claiming them for something that does not exist is how the
registry stops being true.

```yaml
# The registry every application derives from. One entry per app.
#
# Adding an entry is a pull request to this repository; `bin/provision <app>`
# then creates the database and the role. The ingress, the apex page and the
# list of databases the backup job dumps are all generated from this file.
apps:
  - name: media
    hostname: media.cg1618.com
    port: 8000
    database: media
    repo: git@github.com:cg1618-apps/media.git
    exposure: public
    health_path: /api/health
    description: Media tracker & database
```

- [ ] **Step 3: Write the schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "cg1618 application registry",
  "type": "object",
  "required": ["apps"],
  "additionalProperties": false,
  "properties": {
    "apps": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["name", "hostname", "port", "database", "repo", "exposure", "health_path", "description"],
        "additionalProperties": false,
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
          "hostname": {"type": "string", "pattern": "^[a-z0-9.-]+\\.cg1618\\.com$"},
          "port": {"type": "integer", "minimum": 8000, "maximum": 8099},
          "database": {"type": ["string", "null"], "pattern": "^[a-z][a-z0-9_]*$"},
          "repo": {"type": "string", "pattern": "^git@github\\.com:cg1618-apps/[a-z0-9-]+\\.git$"},
          "exposure": {"enum": ["public", "cloudflare-access", "lan-only"]},
          "health_path": {"type": "string", "pattern": "^/"},
          "description": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

`database` accepts `null` because the spec says an app need not have one. Note
that a JSON Schema `pattern` does not apply to `null`, so the null case passes
by type alone — which is the intent.

- [ ] **Step 4: Write the failing test**

```python
"""apps.yml must match the schema that describes it."""

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "apps.yml"
SCHEMA = ROOT / "schema" / "apps.schema.json"


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry():
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def test_registry_matches_the_schema(registry, schema):
    jsonschema.validate(instance=registry, schema=schema)


def test_media_is_registered(registry):
    names = [app["name"] for app in registry["apps"]]
    assert "media" in names


def test_an_unknown_field_is_rejected(schema):
    # additionalProperties: false is the whole point - a typo'd key must fail
    # rather than being silently ignored by every generator downstream.
    bad = {"apps": [{
        "name": "media", "hostname": "media.cg1618.com", "port": 8000,
        "database": "media", "repo": "git@github.com:cg1618-apps/media.git",
        "exposure": "public", "health_path": "/api/health",
        "description": "x", "prot": 8001,
    }]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_an_unknown_exposure_is_rejected(schema):
    bad = {"apps": [{
        "name": "media", "hostname": "media.cg1618.com", "port": 8000,
        "database": "media", "repo": "git@github.com:cg1618-apps/media.git",
        "exposure": "world-readable", "health_path": "/api/health",
        "description": "x",
    }]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)
```

- [ ] **Step 5: Run it**

```bash
cd /c/Users/cgent/Documents/cg1618
# There is no system `python` on PATH on either machine. Build this venv from
# the media tracker's interpreter, the same way worktree.ps1 does.
media/venv/Scripts/python.exe -m venv venv
venv/Scripts/python.exe -m pip install -r requirements-dev.txt
venv/Scripts/python.exe -m pytest tests/test_apps_schema.py -v
```

Expected: four passed. If `test_an_unknown_field_is_rejected` fails, the schema
is missing `additionalProperties: false` — fix the schema, not the test.

- [ ] **Step 6: Commit**

```bash
git add apps.yml schema/apps.schema.json tests/test_apps_schema.py requirements-dev.txt
git commit -m "feat: the application registry and the schema it must match"
```

---

### Task 4: The policy validator

A schema describes one entry. Policy is about the relationships **between**
entries, and about which values are allowed for which app.

**Files:**
- Create: `bin/validate_apps.py`
- Create: `tests/test_validate_apps.py`

**Interfaces:**
- Consumes: `apps.yml` and `schema/apps.schema.json` from Task 3.
- Produces: `validate(registry: dict) -> list[str]` in `bin/validate_apps.py`,
  returning one human-readable string per violation and an empty list when the
  registry is clean. `main(argv: list[str] | None = None) -> int` returns 0 or 1
  and prints each violation to stderr. Task 5's workflow calls
  `python bin/validate_apps.py`; step 4 of the overall sequence calls the same
  module from `bin/deploy`.

- [ ] **Step 1: Write the failing test**

The negative cases matter more than the positive one here, and each needs a
registry that actually contains the thing being refused — a uniqueness rule
passes vacuously on a one-app file, which is exactly what `apps.yml` is today.

```python
"""The policy apps.yml must satisfy, beyond its shape."""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

from validate_apps import validate  # noqa: E402


def app(**overrides):
    base = {
        "name": "media",
        "hostname": "media.cg1618.com",
        "port": 8000,
        "database": "media",
        "repo": "git@github.com:cg1618-apps/media.git",
        "exposure": "public",
        "health_path": "/api/health",
        "description": "Media tracker & database",
    }
    base.update(overrides)
    return base


def test_the_real_registry_is_clean():
    registry = yaml.safe_load((ROOT / "apps.yml").read_text(encoding="utf-8"))
    assert validate(registry) == []


def test_two_apps_may_not_share_a_hostname():
    registry = {"apps": [app(), app(name="food", port=8001, database="food",
                              repo="git@github.com:cg1618-apps/food.git")]}
    problems = validate(registry)
    assert any("media.cg1618.com" in p for p in problems)


def test_two_apps_may_not_share_a_port():
    registry = {"apps": [app(), app(name="food", hostname="food.cg1618.com",
                                    database="food",
                                    repo="git@github.com:cg1618-apps/food.git")]}
    assert any("port 8000" in p for p in validate(registry))


def test_two_apps_may_not_share_a_database():
    registry = {"apps": [app(), app(name="food", hostname="food.cg1618.com",
                                    port=8001,
                                    repo="git@github.com:cg1618-apps/food.git")]}
    assert any("database 'media'" in p for p in validate(registry))


def test_two_apps_may_share_no_database():
    # null is legal and repeatable - "no database" is not a collision.
    registry = {"apps": [
        app(database=None),
        app(name="food", hostname="food.cg1618.com", port=8001, database=None,
            repo="git@github.com:cg1618-apps/food.git"),
    ]}
    assert validate(registry) == []


@pytest.mark.parametrize("name", ["journal", "health", "money"])
def test_the_private_three_may_not_be_public(name):
    registry = {"apps": [app(name=name, hostname=f"{name}.cg1618.com",
                             port=8001, database=name,
                             repo=f"git@github.com:cg1618-apps/{name}.git",
                             exposure="public")]}
    assert any(name in p and "public" in p for p in validate(registry))


@pytest.mark.parametrize("name", ["journal", "health", "money"])
def test_the_private_three_are_fine_behind_access(name):
    registry = {"apps": [app(name=name, hostname=f"{name}.cg1618.com",
                             port=8001, database=name,
                             repo=f"git@github.com:cg1618-apps/{name}.git",
                             exposure="cloudflare-access")]}
    assert validate(registry) == []


def test_the_app_name_must_match_its_repository():
    registry = {"apps": [app(repo="git@github.com:cg1618-apps/medja.git")]}
    assert any("medja" in p for p in validate(registry))
```

- [ ] **Step 2: Run it and watch it fail**

```bash
venv/Scripts/python.exe -m pytest tests/test_validate_apps.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'validate_apps'`.

- [ ] **Step 3: Write the validator**

```python
#!/usr/bin/env python3
"""Check apps.yml against the policy a JSON Schema cannot express.

Two kinds of rule live here. Uniqueness is relational - it is about pairs of
entries, which a schema validates one at a time and so cannot see. And the
exposure rule is about which value is allowed for which app, which a schema
could only express as an enum per app name, restated every time an app is
added.

This runs in CI, and again inside bin/deploy on the box. Shifting a check left
is not a reason to trust that it ran - the same reason deploy.sh re-checks
MIGRATION_APPROVED rather than believing GitHub's gate.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "apps.yml"
SCHEMA = ROOT / "schema" / "apps.schema.json"

# These hold a different class of data. The Cloudflare Access decision belongs
# before the ingress rule exists, not after it has been serving.
NEVER_PUBLIC = ("journal", "health", "money")


def validate(registry: dict) -> list[str]:
    """Return one message per policy violation; empty means clean."""
    problems: list[str] = []
    apps = registry.get("apps", [])

    for field, label in (("hostname", "hostname"), ("port", "port")):
        counts = Counter(a[field] for a in apps)
        for value, count in sorted(counts.items(), key=lambda kv: str(kv[0])):
            if count > 1:
                problems.append(f"{count} apps claim {label} {value}")

    databases = Counter(a["database"] for a in apps if a["database"] is not None)
    for value, count in sorted(databases.items()):
        if count > 1:
            problems.append(f"{count} apps claim database {value!r}")

    for a in apps:
        if a["name"] in NEVER_PUBLIC and a["exposure"] == "public":
            problems.append(
                f"{a['name']} is exposure 'public'; it holds a different class "
                f"of data and must be 'cloudflare-access' or 'lan-only'"
            )
        expected_repo = f"git@github.com:cg1618-apps/{a['name']}.git"
        if a["repo"] != expected_repo:
            problems.append(
                f"{a['name']} names repository {a['repo']!r}, expected {expected_repo!r}"
            )

    return problems


def main(argv: list[str] | None = None) -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    try:
        jsonschema.validate(instance=registry, schema=schema)
    except jsonschema.ValidationError as exc:
        print(f"apps.yml does not match the schema: {exc.message}", file=sys.stderr)
        return 1

    problems = validate(registry)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests again**

```bash
venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all pass. Then prove the entry point behaves:

```bash
venv/Scripts/python.exe bin/validate_apps.py && echo "registry clean"
```

Expected: `registry clean`, exit 0.

- [ ] **Step 5: Prove the validator bites on the real file**

A refusal test that never saw a refusal is the failure mode this project has
already been bitten by. Break `apps.yml` on purpose, confirm the exit code, then
put it back.

```bash
cp apps.yml /tmp/apps.yml.bak
sed -i "s/exposure: public/exposure: worldwide/" apps.yml
venv/Scripts/python.exe bin/validate_apps.py; echo "exit=$?"   # expect exit=1
cp /tmp/apps.yml.bak apps.yml
git diff --exit-code apps.yml && echo "restored"
```

- [ ] **Step 6: Commit**

```bash
git add bin/validate_apps.py tests/test_validate_apps.py
git commit -m "feat: validate the policy a schema cannot express"
```

---

### Task 5: The `Tests` workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `requirements-dev.txt`, `tests/`, `bin/validate_apps.py`.
- Produces: a workflow named `Tests` whose job id is **`test`** — the ruleset in
  Task 6 requires that exact context string.

- [ ] **Step 1: Write the workflow**

```yaml
name: Tests

# Pull requests only, and ubuntu-latest only. The self-hosted runner is a
# machine in a house, every repository here is public, and a fork's pull
# request running on it is the standard catastrophe. No pull_request-triggered
# job may ever name it.
on:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Validate the registry
        run: python bin/validate_apps.py

      - name: Run the tests
        run: python -m pytest tests/ -q

      - name: Lint the workflows
        uses: raven-actions/actionlint@v2

      - name: Lint the shell scripts
        run: |
          if compgen -G "bin/*.sh" > /dev/null; then
            sudo apt-get update && sudo apt-get install -y shellcheck
            shellcheck bin/*.sh
          else
            echo "No shell scripts yet."
          fi
```

`shellcheck` is guarded because `bin/` holds no `.sh` files until step 4 of the
overall sequence moves the deploy scripts here; an unguarded glob fails the job
on a repository that is simply not there yet.

- [ ] **Step 2: Commit and push the branch**

```bash
git checkout -b feat/registry
git add .github/workflows/ci.yml
git commit -m "ci: validate the registry on every pull request"
git push -u origin feat/registry
```

Note that Tasks 3 and 4 committed to `dev` directly while the repository had no
protection. From here on everything goes through a branch — and Task 6's ruleset
makes that structural rather than a habit.

- [ ] **Step 3: Open the pull request and watch the check run**

Show the owner the title and body first; opening and merging are theirs.

Expected: a check named `test` appears, runs on `ubuntu-latest`, and passes.

---

### Task 6: The ruleset

**Files:** none — GitHub-side.

**Interfaces:**
- Consumes: the `test` check from Task 5, which must have run at least once for
  GitHub to offer it by name.
- Produces: a ruleset named `Protected Branches` on `main` and `dev`, requiring
  a pull request and a passing `test`.

- [ ] **Step 1: Copy the media tracker's ruleset definition**

It is already the arrangement wanted, and copying it means the two repositories
cannot drift by accident.

```bash
gh api repos/cg1618-apps/media/rulesets --jq '.[] | select(.name=="Protected Branches") | .id'
gh api repos/cg1618-apps/media/rulesets/<id> > /tmp/ruleset.json
```

- [ ] **Step 2: Create the same ruleset on `platform`**

```bash
jq '{name, target, enforcement, conditions, rules}' /tmp/ruleset.json \
  | gh api -X POST repos/cg1618-apps/platform/rulesets --input -
```

Browser equivalent: Settings → Rules → Rulesets → New branch ruleset. Name
`Protected Branches`, enforcement Active, targets `refs/heads/main` and
`refs/heads/dev`, and enable: restrict deletions, block force pushes, require a
pull request before merging (0 approvals, require extra approval for
unattributed changes), require status checks to pass with **`test`** and
"require branches to be up to date".

- [ ] **Step 3: Verify it is active and names the right check**

```bash
gh api repos/cg1618-apps/platform/rulesets --jq '.[] | {name, enforcement}'
gh api repos/cg1618-apps/platform/rulesets/<new-id> \
  --jq '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context]'
```

Expected: `active`, and `["test"]`.

- [ ] **Step 4: Prove the gate bites**

The check that a gate refuses is worth more than the check that it allows, and
it is the one nobody runs. Push a deliberate violation on a branch, confirm the
pull request is blocked, then close it.

```bash
git checkout -b test/ruleset-bites
python - <<'PY'
import io
s = io.open("apps.yml", encoding="utf-8").read()
io.open("apps.yml", "w", encoding="utf-8", newline="\n").write(
    s.replace("exposure: public", "exposure: worldwide"))
PY
git commit -m "test: an invalid registry, to prove the check refuses it" -- apps.yml
git push -u origin test/ruleset-bites
```

Open a pull request from it. Expected: `test` **fails** on the schema's
`exposure` enum, and the pull request reads `BLOCKED` rather than mergeable.
Then close the pull request and delete the branch:

```bash
gh pr close <n> -R cg1618-apps/platform
git push origin --delete test/ruleset-bites
git checkout dev && git branch -D test/ruleset-bites
```

Record the result in the pull request that follows, because this is the only
evidence the required check is real rather than configured.

---

### Task 7: Point the documentation at the new repository

**Files:**
- Modify: `C:\Users\cgent\Documents\cg1618\media\docs\switching-environments.md`
- Modify: `C:\Users\cgent\Documents\cg1618\media\docs\notes\decisions.md`

**Interfaces:**
- Consumes: a working `cg1618-apps/platform`.
- Produces: a media-repository pull request recording that the platform repo
  exists and what it holds.

- [ ] **Step 1: Record the second repository on this machine**

In `docs/switching-environments.md`, under the machine table, state that
`Documents\cg1618` is itself a clone of `cg1618-apps/platform` with `media`
nested inside it and ignored by it, and that a session working on
infrastructure runs from `cg1618\` while a session working on the tracker runs
from `cg1618\media\`.

- [ ] **Step 2: Record what landed, in `decisions.md`**

Under the existing "Multi-app platform topology" section, one bullet: the
registry exists, the validator runs in CI and again in `bin/deploy` later, and
the generators are deliberately deferred to the steps that move the files they
generate.

- [ ] **Step 3: Bump `Last verified` on `switching-environments.md`, commit, PR**

Docs only, so the media suite need not run locally; its own `test` check covers
the pull request.

---

## What this step deliberately does not do

- **No generators.** The cloudflared ingress and the apex navigation derive from
  `apps.yml`, but both live in files that have not moved yet. Generating them
  here would produce output nothing consumes, and a drift check against a file
  the box does not read. They arrive with steps 3 and 6.
- **No `bin/provision`, no `bin/deploy`.** Step 4, after the split, because
  their shape depends on it.
- **Nothing moves off the media tracker**, so
  `tests/unit/test_prod_compose.py` keeps guarding the live ingress and
  `deploy/` keeps working exactly as it does now. Production is untouched by
  every task above.
- **No entries for the six planned applications.** An entry claims a hostname, a
  port and a database; claiming them for something that does not exist is how a
  registry stops being true. They arrive with `bin/provision`.

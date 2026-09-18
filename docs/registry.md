# The application registry

Last verified: 2026-09-18

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
    repo: git@github.com:cg1618-apps/media.git
    exposure: public         # public | cloudflare-access | lan-only
    health_path: /api/health
    description: Media tracker & database
```

`health_path` is declared rather than assumed because the applications do not
share a stack. `/api/health` is the media tracker's answer — it opens a real
database session and compares `alembic_version` to the head the running code
expects — not a platform fact. An app written against something else exposes
something else, so the app declares it and the deploy script reads it.

Only applications that **exist** are listed. An entry claims a hostname, a port
and a database; claiming them for something unbuilt is how a registry stops
being true.

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
- **That each app names its own repository**, so a copy-pasted entry cannot
  point two apps at one repo.

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

## Adding an application

1. A pull request to this repository adding its `apps.yml` entry. The ingress,
   the port and the database follow from it.
2. `bin/provision <app>` once, when it exists.
3. A new repository in `cg1618-apps` satisfying the app contract: a container on
   the port this file assigns, the health path it declares here, `DATABASE_URL`
   from the environment, and a `main` branch that is production.

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

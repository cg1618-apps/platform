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
- `docs/registry.md` — what `apps.yml` guarantees, and how an app is added.
- `docs/` — how the box is arranged and why.

`main` is production and moves only by a release pull request from `dev`.

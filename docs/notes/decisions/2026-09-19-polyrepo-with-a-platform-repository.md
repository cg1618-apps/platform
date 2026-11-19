# Polyrepo, with a platform repository as the master

One repository per app, plus `cg1618-apps/platform` holding what is shared:
`apps.yml`, the apex page, the cloudflared ingress, the shared PostgreSQL, the
deploy scripts, the box documentation and the generic `CLAUDE.md`.

**Rejected: a monorepo.** The apps do not share code. They share a box, a
database server and a tunnel, and all three are the platform's. One repository
would also put every app's CI on every app's pull request.

**The cost accepted:** a change spanning the platform and an app is two pull
requests in sequence, and the two halves cannot land in one commit. That cost
is paid regularly.

# App checkouts nest inside the platform checkout

Each app is cloned at `cg1618/<app>`, as its own repository, and ignored by
the platform. It reads like a monorepo and is not one.

**Why:** a tool opened anywhere in the tree finds the platform's `CLAUDE.md`
by walking upward. So the generic rules load for every app without being
copied into each one.

**The cost accepted:** a careless `pytest` or `ruff` at the platform root
walks into the app checkouts. That is why the platform's own commands name
`tests/` explicitly, and why `pytest.ini` pins `testpaths`.

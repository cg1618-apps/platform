# A gated path is defined by the app; the registry declares it and is checked

A `public` app keeps its write surface under its own path prefix behind
Access. `exposure` is one enum for a whole app, and probing
`https://<hostname>` alone cannot see that prefix: a public app answers
ungated at the root, correctly, with or without its writes protected. What
ships is in `docs/registry.md`: the app's `deploy/gated-paths`, the registry's
`gated_paths`, and the refusal when they disagree.

**The app is the authority.** Which paths an app's writes live on is a fact
about its route table, found only in that repository and changed only by a
commit there. A prefix typed by hand into `apps.yml` is a transcription of
something that lives elsewhere, and it goes stale silently the moment a route
moves. That is the opposite of `hostname`, `port` and `database`, which the
platform *allocates* and the app receives, and which are correctly
registry-owned.

**Two copies, accepted deliberately.** `migrations` in `apps.yml` is a
boolean, because `bin/deploy` only needs to know whether a hook should exist
and has the hook itself to run. `gated_paths` holds the values instead,
because `bin/check-exposure --all` runs from this repository against the open
internet with no app checkout, and needs the path strings to have anything to
probe. The drift between the two copies is made loud at deploy, where
`bin/deploy` refuses in either direction.

Rejected:

- **The registry as the only copy.** It goes stale as described above, with
  nothing to notice.
- **Making the check runnable only from the box**, where the app checkouts
  are, so the registry needs no copy. It would take `bin/check-exposure --all`
  away from every development machine.
- **Leaving the registry silent and the policy Cloudflare-side only.**
  Cheaper, and it reproduces exactly the gap `bin/check-exposure` exists to
  close: a gate asserted in a dashboard this repository cannot see, with
  nothing connecting the claim to the reality.

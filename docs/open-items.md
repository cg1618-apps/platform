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

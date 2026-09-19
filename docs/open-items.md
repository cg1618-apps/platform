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

The decision is which of these it is, and it is the platform's to make, not an
app's:

1. A registry key — something like `gated_paths: ["/api/edit"]` — that
   `bin/check-exposure` probes for the Access redirect, the way it already
   probes the root. Keeps the claim and the check in the same place as every
   other exposure claim.
2. Cloudflare-side only: the Access policy covers the path, and the registry
   stays silent about it. Cheaper now, and it reproduces exactly the gap that
   `bin/check-exposure` was written to close after `art` served
   unauthenticated for twenty minutes.
3. The app authenticates its own writes and Access is not involved. Moves the
   gate into code, which then needs refusal tests with fixtures that make
   refusal possible.

Option 1 is the one consistent with how everything else here works — the
registry states intent and a script asks the open internet whether reality
agrees.

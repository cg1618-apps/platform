# `media` is the reference because it is read, not because it is right

`CLAUDE.md`, "House style", names `media` the reference the other apps copy
conventions from. That rule stands. It must not be read as `media` being where
the truth lives: when it was written, `media` was measurably wrong in places
where the apps copying it were right.

The instances:

- **Migration naming.** `media` uses mnemonic revision ids throughout.
  `food`, `travel` and `art` each carry `0001_baseline.py` from the same app
  skeleton, so three of four apps agreed, and all three were inheriting one
  decision nobody made. Reading the neighbours rather than the reference sent
  `travel` to `0002_packing`, and very nearly sent a "correction" to `food`,
  the only new app actually following `media`.
- **`strictPort`.** `food`, `travel` and `art` set it in their Vite config;
  `media` does not. The copies made a choice the reference never revisited.
- **The frontend fetch wrapper.** `media`'s rendered an array-shaped Pydantic
  422 as `[object Object]` and discarded the status code, which made its own
  documented 409 contract unusable. `food` did not inherit either, because when
  it asked about the convention it was told to write the fixed wrapper rather
  than copy the shipped one.

**What protected `food` was not `media` being correct.** It was `media` being
asked to justify itself and answering honestly.

So: **read the reference rather than the neighbours**, because the neighbours
may all be inheriting one unmade decision, and **ask the reference why**,
because a convention may be a starting point nobody revisited. An app that
finds the reference wrong and says so is the rule working. What the rule
rules out is diverging silently, not diverging.

**This is not a base rate, and reading it as one inverts the rule.** These
surfaced together because one app was asking convention questions in detail
and every answer was checked against the file. The conclusion is that the
reference has to defend itself when asked, not that it is usually wrong. An
app that stops reading `media` because of this will reinvent conventions that
were right all along. Ask, and believe the answer when it holds up.

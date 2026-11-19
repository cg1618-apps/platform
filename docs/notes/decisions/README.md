# Decisions

One file per decision, named `YYYY-MM-DD-<topic>.md` after the day it was
made. Each holds a `# Title`, the reasoning, and the alternatives that were
rejected, so nobody proposes them again unaware.

- **No index.** The date-prefixed file names are the index. A list here would
  be a file every pull request appends to, which is the conflict one file per
  decision exists to avoid.
- **Why, not what.** Present-tense behaviour, rules and procedure go on the
  matching page under `docs/`. A decision file keeps only reasoning that
  still binds.
- **Delete a decision when it stops binding.** A decision about code that no
  longer exists, or one a later decision reversed, is history, and git keeps
  it. A reversal gets its own new file, and the file it overturns is deleted
  in the same commit.

The rule is in `CLAUDE.md`, "Decisions are one file each".

# Apps emit streams; the box aggregates

**An application's logging obligation ends at stdout**, and one collector on
the box aggregates every container's stream. There is no per-app log system
and no bespoke integrated one. The contract is `docs/logging.md`; the stack is
`docs/shared-stack.md`, "Observability".

**Rejected: each app owning a log viewer, joined up later.** The apps share a
box, a database server and a tunnel, and those are the platform's; so is
this. Four log viewers would be four implementations of one thing, diverging
the way four of anything here diverges, and the integration would still have
to be written afterwards against four shapes instead of one. The leverage is
on the platform side: an app's half is a `dictConfig` and a middleware, done
once, while one collector gains every app the day it is switched on,
including the apps nobody is working in.

**Loki, Alloy and Grafana rather than ELK.** All are free and self-hostable;
Elasticsearch would eat a mini PC on its own. Loki indexes labels rather than
full text, which fits a box where the question is almost always "what did this
container do around this time" rather than "find this word anywhere in a
year". All three are Grafana Labs OSS (Loki and Grafana AGPLv3, Alloy Apache
2.0), with no Grafana Cloud or Enterprise involved.

Resources were the only real objection, and were measured before committing:
the box had about 14 GB of 15 GB RAM free, and the stack's expected
400-500 MB is a few percent of it. **Dozzle** (one container, live tail,
stores nothing) was the fallback had the box been tight. It is not the same
product: it has no history, and history is half the point.

**Audit trails are not this.** "Who changed this entry", "Pull All rewrote 312
rows" is domain data about a user's own records. It belongs in the app's own
PostgreSQL and its own UI, queried by a person asking about their data, not by
someone working out why the box misbehaves. Conflating the two produces a log
system that is also a weak database, and an audit trail that disappears on a
container recreate.

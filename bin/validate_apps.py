#!/usr/bin/env python3
"""Check apps.yml against the policy a JSON Schema cannot express.

Two kinds of rule live here. Uniqueness is relational - it is about pairs of
entries, which a schema validates one at a time and so cannot see. And the
exposure rule is about which value is allowed for which app, which a schema
could only express as an enum per app name, restated every time an app is
added.

`gated_paths` needs a rule here for the same reason as exposure: which values
are allowed depends on another field of the same entry, which a schema can only
express by restating the entry. What it protects lives elsewhere too - bin/deploy
refuses when this list and the app's own deploy/gated-paths disagree, and
bin/check-exposure probes each path from the open internet.

`migrations` needs no rule here - it is per-entry and boolean, so the schema's
`required` list is the whole check. It is listed in this docstring anyway
because the thing it protects is not in this file: bin/deploy and bin/rollback
read it, and an app declaring `true` with no executable deploy/migrations is
refused there rather than deployed with no approval gate.

This runs in CI, and later again inside bin/deploy on the box. Shifting a check
left is not a reason to trust that it ran - the same reason deploy.sh re-checks
MIGRATION_APPROVED rather than believing GitHub's gate.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "apps.yml"
SCHEMA = ROOT / "schema" / "apps.schema.json"

# These hold a different class of data. The Cloudflare Access decision belongs
# before the ingress rule exists, not after it has been serving.
NEVER_PUBLIC = ("journal", "health", "money")

# The schema reserves 8000-8099. Apps take the bottom of that block and every
# worktree allocates from WORKTREE_FLOOR upward, because a worktree needs a
# port no app entry can ever claim - see docs/dev-ports.md. Registering an app
# at or above the floor would put it in the band worktrees hand out, and the
# collision surfaces as somebody else's app failing to bind hours later, with
# nothing pointing back at the worktree that took it.
WORKTREE_FLOOR = 8050


def validate(registry: dict) -> list[str]:
    """Return one message per policy violation; empty means clean."""
    problems: list[str] = []
    apps = registry.get("apps", [])

    for field, label in (("hostname", "hostname"), ("port", "port")):
        counts = Counter(a[field] for a in apps)
        for value, count in sorted(counts.items(), key=lambda kv: str(kv[0])):
            if count > 1:
                problems.append(f"{count} apps claim {label} {value}")

    databases = Counter(a["database"] for a in apps if a["database"] is not None)
    for value, count in sorted(databases.items()):
        if count > 1:
            problems.append(f"{count} apps claim database {value!r}")

    for a in apps:
        if a["name"] in NEVER_PUBLIC and a["exposure"] == "public":
            problems.append(
                f"{a['name']} is exposure 'public'; it holds a different class "
                f"of data and must be 'cloudflare-access' or 'lan-only'"
            )
        # `gated_paths` only means anything on a public app. A
        # cloudflare-access hostname is gated at every path already, and
        # lan-only has no ingress rule at all - so declaring a gated prefix
        # on either is a statement about a gate that is not where the entry
        # says it is, and bin/check-exposure would "confirm" it by finding
        # the redirect the whole hostname already returns.
        gated = a.get("gated_paths") or []
        if gated and a["exposure"] != "public":
            problems.append(
                f"{a['name']} declares gated_paths but is exposure "
                f"{a['exposure']!r}; that value already gates every path, so "
                f"a prefix here would be confirmed by the hostname's own gate"
            )
        for path in gated:
            if path == "/":
                problems.append(
                    f"{a['name']} declares gated_paths '/'; gating every path "
                    f"is exposure 'cloudflare-access', not a public app with a "
                    f"prefix"
                )

        if a["port"] >= WORKTREE_FLOOR:
            problems.append(
                f"{a['name']} claims port {a['port']}; apps keep below "
                f"{WORKTREE_FLOOR} and worktrees allocate from there upward, "
                f"so this port is one a worktree may already be using"
            )

        expected_repo = f"git@github.com:cg1618-apps/{a['name']}.git"
        if a["repo"] != expected_repo:
            problems.append(
                f"{a['name']} names repository {a['repo']!r}, expected {expected_repo!r}"
            )

    return problems


def main(argv: list[str] | None = None) -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    try:
        jsonschema.validate(instance=registry, schema=schema)
    except jsonschema.ValidationError as exc:
        print(f"apps.yml does not match the schema: {exc.message}", file=sys.stderr)
        return 1

    problems = validate(registry)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

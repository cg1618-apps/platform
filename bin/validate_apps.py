#!/usr/bin/env python3
"""Check apps.yml against the policy a JSON Schema cannot express.

Two kinds of rule live here. Uniqueness is relational - it is about pairs of
entries, which a schema validates one at a time and so cannot see. And the
exposure rule is about which value is allowed for which app, which a schema
could only express as an enum per app name, restated every time an app is
added.

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

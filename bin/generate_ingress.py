#!/usr/bin/env python3
"""Render the Cloudflare Tunnel ingress from apps.yml.

Hand-editing the ingress is how a hostname ends up routed that nobody decided
to route. The registry is where an app's exposure is decided - and where
bin/validate_apps.py refuses `public` for journal, health and money - so the
ingress is derived from it, and CI fails when the committed output has drifted.

The generated file is committed rather than built at deploy time, because the
ingress that will actually be served then appears in the pull request diff,
where a person reads it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "apps.yml"
OUTPUT = ROOT / "cloudflared" / "config.yml"

HEADER = """\
# GENERATED FROM apps.yml BY bin/generate_ingress.py - DO NOT EDIT.
#
# Regenerate with `python bin/generate_ingress.py`; CI fails if this file and
# apps.yml disagree. Add a hostname by adding its app to apps.yml, which is
# also where exposure is decided and where journal, health and money are
# refused `public`.
#
# The tunnel's id is NOT here. It is passed on the command line from TUNNEL_ID
# in the platform's .env, which keeps this file static and committable - it can
# be written before the tunnel exists. The id is not a secret either way; the
# credentials JSON is, and it is mounted read-only from a path the .env names.

credentials-file: /etc/cloudflared/credentials.json

ingress:
"""

CATCH_ALL = """
  # Required catch-all. cloudflared refuses to start without it, and it must be
  # the last rule.
  - service: http_status:404
"""


def render(registry: dict) -> str:
    """Return the full contents of cloudflared/config.yml."""
    parts = [HEADER]
    for app in registry["apps"]:
        # The tunnel is the public path, so "lan-only" is implemented by the
        # absence of a rule rather than by anything written here.
        if app["exposure"] == "lan-only":
            continue
        if app["exposure"] == "cloudflare-access":
            parts.append(
                f"  # {app['name']}: cloudflare-access - Cloudflare enforces\n"
                f"  # authentication in front of this rule.\n"
            )
        # The service name is the app's network alias in its own compose
        # project: <name>-app. An app that changes that alias without changing
        # apps.yml gets a 502 on its hostname.
        parts.append(
            f"  - hostname: {app['hostname']}\n"
            f"    service: http://{app['name']}-app:{app['port']}\n"
        )
    parts.append(CATCH_ALL)
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    rendered = render(registry)

    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != rendered:
            print(
                f"{OUTPUT.relative_to(ROOT).as_posix()} does not match apps.yml. "
                f"Run `python bin/generate_ingress.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(rendered)
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

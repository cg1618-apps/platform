#!/usr/bin/env python3
"""Render the apex page at cg1618.com from apps.yml.

The page is a rendering of the registry and nothing else: it changes exactly
when apps.yml changes, which is why it lives in this repository rather than in
one of its own. The day it needs a backend, a database, authentication or
per-user state it becomes cg1618-apps/landing with its own repo and its own
port - that rule is what keeps "no application code in the infrastructure
repository" honest rather than arbitrary.

Generated and committed, like the ingress, so the page that will be served
appears in the pull request diff. CI fails when it and apps.yml disagree.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "apps.yml"
OUTPUT = ROOT / "apex" / "html" / "index.html"

TEMPLATE = """<!DOCTYPE html>
<!-- GENERATED FROM apps.yml BY bin/generate_apex.py - DO NOT EDIT. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>cg1618</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #fbfaf8;
    --fg: #1b1a18;
    --muted: #6d6a66;
    --line: #e3e0da;
    --accent: #7a5c3e;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #16151a;
      --fg: #eceaf0;
      --muted: #9a96a3;
      --line: #2c2a33;
      --accent: #c9a227;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 4rem 1.5rem;
    background: var(--bg);
    color: var(--fg);
    font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    display: flex;
    justify-content: center;
  }}
  main {{ width: 100%; max-width: 44rem; }}
  h1 {{
    font-size: 1.6rem;
    letter-spacing: 0.02em;
    margin: 0 0 0.25rem;
  }}
  .sub {{ color: var(--muted); margin: 0 0 2.5rem; font-size: 0.95rem; }}
  ul {{ list-style: none; margin: 0; padding: 0; }}
  li {{ border-top: 1px solid var(--line); }}
  li:last-child {{ border-bottom: 1px solid var(--line); }}
  a, .planned {{
    display: flex;
    gap: 1rem;
    align-items: baseline;
    padding: 1.1rem 0.25rem;
    text-decoration: none;
    color: inherit;
  }}
  a:hover {{ background: color-mix(in srgb, var(--accent) 8%, transparent); }}
  .name {{ font-weight: 600; min-width: 5.5rem; }}
  a .name {{ color: var(--accent); }}
  .desc {{ color: var(--muted); font-size: 0.95rem; }}
  .planned {{ opacity: 0.55; cursor: default; }}
  .tag {{
    margin-left: auto;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    white-space: nowrap;
  }}
  footer {{ margin-top: 3rem; color: var(--muted); font-size: 0.82rem; }}
</style>
</head>
<body>
<main>
  <h1>cg1618</h1>
  <p class="sub">Personal applications, self-hosted.</p>
  <ul>
{items}
  </ul>
  <footer>Generated from <code>apps.yml</code>.</footer>
</main>
</body>
</html>
"""

LIVE = """    <li><a href="https://{hostname}">
      <span class="name">{name}</span>
      <span class="desc">{description}</span>
    </a></li>"""

PLANNED = """    <li><div class="planned">
      <span class="name">{name}</span>
      <span class="desc">{description}</span>
      <span class="tag">planned</span>
    </div></li>"""


def render(registry: dict) -> str:
    """Return the full contents of apex/html/index.html."""
    items = []
    for app in registry["apps"]:
        fields = {
            "name": html.escape(app["name"]),
            "hostname": html.escape(app["hostname"]),
            "description": html.escape(app["description"]),
        }
        # A planned app is listed but not linked. Linking it would offer a
        # hostname that is not routed, which reads as the site being broken
        # rather than as the app not existing yet.
        items.append((LIVE if app["status"] == "live" else PLANNED).format(**fields))
    return TEMPLATE.format(items="\n".join(items))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    rendered = render(registry)

    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != rendered:
            print(
                f"{OUTPUT.relative_to(ROOT).as_posix()} does not match apps.yml. "
                f"Run `python bin/generate_apex.py` and commit the result.",
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

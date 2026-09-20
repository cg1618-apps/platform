"""The apex page is a rendering of the registry, never hand-edited."""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

from generate_apex import render  # noqa: E402

REGISTRY = yaml.safe_load((ROOT / "apps.yml").read_text(encoding="utf-8"))


def app(**overrides):
    base = {
        "name": "media",
        "hostname": "media.cg1618.com",
        "port": 8000,
        "database": "media",
        "repo": "git@github.com:cg1618-apps/media.git",
        "exposure": "public",
        "health_path": "/api/health",
        "migrations": True,
        "status": "live",
        "description": "Media tracker & database",
    }
    base.update(overrides)
    return base


def test_the_committed_page_matches_the_registry():
    committed = (ROOT / "apex" / "html" / "index.html").read_text(encoding="utf-8")
    assert committed == render(REGISTRY)


def test_every_app_appears():
    # Escaped, because that is how it reaches the page: "Media tracker &
    # database" is rendered with &amp;. Asserting the raw string here would
    # fail correct output, which is how a test teaches someone to break
    # escaping.
    import html as _html

    page = render(REGISTRY)
    for entry in REGISTRY["apps"]:
        assert entry["name"] in page
        assert _html.escape(entry["description"]) in page


def test_a_live_app_is_linked_at_its_hostname():
    page = render({"apps": [app()]})
    assert 'href="https://media.cg1618.com"' in page


def test_a_planned_app_is_listed_but_not_linked():
    # A link to a hostname the tunnel does not route reads as the site being
    # broken, rather than as the app not existing yet. This is the assertion
    # that has to bite, so the fixture makes it possible: apps.yml today has
    # planned apps in it, but a registry of only live ones would pass this
    # vacuously.
    page = render({"apps": [app(name="food", hostname="food.cg1618.com",
                                status="planned", description="Ingredients")]})
    assert "food" in page
    assert "planned" in page
    assert 'href="https://food.cg1618.com"' not in page
    # Any hostname link, not just food's - the point is that a planned app is
    # linked NOWHERE, so a renamed hostname cannot slip past the line above.
    # Narrower than a bare `"href=" not in page`, which the head's own favicon
    # links would now trip regardless of what the app row renders.
    assert 'href="https://' not in page


def test_html_in_a_description_is_escaped():
    # apps.yml is written by hand and rendered into a page served publicly.
    page = render({"apps": [app(description='<script>alert("x")</script>')]})
    assert "<script>" not in page
    assert "&lt;script&gt;" in page

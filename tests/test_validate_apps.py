"""The policy apps.yml must satisfy, beyond its shape.

The negative cases matter more than the positive one, and each needs a registry
that actually contains the thing being refused. A uniqueness rule is vacuously
satisfied by a one-app file - which is exactly what apps.yml is today - so a
refusal test written against the real registry would pass without the rule ever
firing, and would keep passing through the change that broke it.
"""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

from validate_apps import validate  # noqa: E402


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


def test_the_real_registry_is_clean():
    registry = yaml.safe_load((ROOT / "apps.yml").read_text(encoding="utf-8"))
    assert validate(registry) == []


def test_two_apps_may_not_share_a_hostname():
    registry = {
        "apps": [
            app(),
            app(
                name="food",
                port=8001,
                database="food",
                repo="git@github.com:cg1618-apps/food.git",
            ),
        ]
    }
    assert any("media.cg1618.com" in p for p in validate(registry))


def test_two_apps_may_not_share_a_port():
    registry = {
        "apps": [
            app(),
            app(
                name="food",
                hostname="food.cg1618.com",
                database="food",
                repo="git@github.com:cg1618-apps/food.git",
            ),
        ]
    }
    assert any("port 8000" in p for p in validate(registry))


def test_two_apps_may_not_share_a_database():
    registry = {
        "apps": [
            app(),
            app(
                name="food",
                hostname="food.cg1618.com",
                port=8001,
                repo="git@github.com:cg1618-apps/food.git",
            ),
        ]
    }
    assert any("database 'media'" in p for p in validate(registry))


def test_two_apps_may_share_no_database():
    # null is legal and repeatable - "no database" is not a collision.
    registry = {
        "apps": [
            app(database=None),
            app(
                name="food",
                hostname="food.cg1618.com",
                port=8001,
                database=None,
                repo="git@github.com:cg1618-apps/food.git",
            ),
        ]
    }
    assert validate(registry) == []


@pytest.mark.parametrize("name", ["journal", "health", "money"])
def test_the_private_three_may_not_be_public(name):
    registry = {
        "apps": [
            app(
                name=name,
                hostname=f"{name}.cg1618.com",
                port=8001,
                database=name,
                repo=f"git@github.com:cg1618-apps/{name}.git",
                exposure="public",
            )
        ]
    }
    assert any(name in p and "public" in p for p in validate(registry))


@pytest.mark.parametrize("name", ["journal", "health", "money"])
def test_the_private_three_are_fine_behind_access(name):
    # The mirror of the test above, on the same fixture: a green there has to
    # mean the exposure rule did the refusing, not something incidental.
    registry = {
        "apps": [
            app(
                name=name,
                hostname=f"{name}.cg1618.com",
                port=8001,
                database=name,
                repo=f"git@github.com:cg1618-apps/{name}.git",
                exposure="cloudflare-access",
            )
        ]
    }
    assert validate(registry) == []


def test_the_app_name_must_match_its_repository():
    registry = {"apps": [app(repo="git@github.com:cg1618-apps/medja.git")]}
    assert any("medja" in p for p in validate(registry))


# `gated_paths` says a PUBLIC app keeps its write surface behind Access on its
# own prefix. Every refusal below needs an entry that actually carries a path -
# an app with no gated_paths satisfies all of these vacuously, and the real
# registry had exactly none of them until food's first write endpoint. Each
# refusal asserts its mirror on the same fixture, so a green proves the rule
# did the refusing rather than the fixture being empty.


def test_a_public_app_may_declare_a_gated_prefix():
    registry = {"apps": [app(gated_paths=["/api/edit"])]}
    assert validate(registry) == []


def test_gated_paths_are_refused_on_a_cloudflare_access_app():
    registry = {"apps": [app(exposure="cloudflare-access", gated_paths=["/api/edit"])]}
    problems = validate(registry)
    assert any("gated_paths" in p for p in problems)


def test_gated_paths_are_refused_on_a_lan_only_app():
    registry = {"apps": [app(exposure="lan-only", gated_paths=["/api/edit"])]}
    assert any("gated_paths" in p for p in validate(registry))


def test_the_same_entry_is_clean_once_it_is_public():
    # The mirror of the two above, on the same fixture: it is the exposure
    # value that is refused, not the presence of the key.
    registry = {"apps": [app(exposure="public", gated_paths=["/api/edit"])]}
    assert validate(registry) == []


def test_gating_the_root_is_refused():
    # Gating every path is what `cloudflare-access` means. Declaring it as a
    # prefix on a public app would have bin/check-exposure confirm the gate by
    # finding the redirect the whole hostname already returns.
    registry = {"apps": [app(gated_paths=["/"])]}
    assert any("'/'" in p for p in validate(registry))


def test_a_deep_path_is_not_refused():
    # Mirror of the root case: the rule is about "/" exactly, not about paths
    # being short or shallow.
    registry = {"apps": [app(gated_paths=["/api"])]}
    assert validate(registry) == []


# Apps keep the bottom of the reserved 8000-8099 block; worktrees allocate from
# WORKTREE_FLOOR upward. The registry cannot see a worktree, so this is the only
# side of that contract it can hold - and it holds it for an app that does not
# exist yet, which is the only moment the rule is cheap.


def test_an_app_may_not_register_in_the_worktree_band():
    registry = {"apps": [app(port=8050)]}
    assert any("8050" in p for p in validate(registry))


def test_an_app_well_inside_the_worktree_band_is_refused():
    registry = {"apps": [app(port=8091)]}
    assert any("worktree" in p for p in validate(registry))


def test_the_port_just_below_the_floor_is_allowed():
    # The mirror: the rule is a floor, not a dislike of high ports. Without
    # this, narrowing the band to nothing would still pass the two above.
    registry = {"apps": [app(port=8049)]}
    assert validate(registry) == []

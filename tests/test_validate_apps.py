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

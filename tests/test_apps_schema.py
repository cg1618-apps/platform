"""apps.yml must match the schema that describes it."""

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "apps.yml"
SCHEMA = ROOT / "schema" / "apps.schema.json"


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry():
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def test_registry_matches_the_schema(registry, schema):
    jsonschema.validate(instance=registry, schema=schema)


def test_media_is_registered(registry):
    names = [app["name"] for app in registry["apps"]]
    assert "media" in names


def test_an_unknown_field_is_rejected(schema):
    # additionalProperties: false is the whole point - a typo'd key must fail
    # rather than being silently ignored by every generator downstream.
    bad = {
        "apps": [
            {
                "name": "media",
                "hostname": "media.cg1618.com",
                "port": 8000,
                "database": "media",
                "repo": "git@github.com:cg1618-apps/media.git",
                "exposure": "public",
                "health_path": "/api/health",
                "migrations": True,
                "status": "live",
                "description": "x",
                "prot": 8001,
            }
        ]
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_an_unknown_exposure_is_rejected(schema):
    bad = {
        "apps": [
            {
                "name": "media",
                "hostname": "media.cg1618.com",
                "port": 8000,
                "database": "media",
                "repo": "git@github.com:cg1618-apps/media.git",
                "exposure": "world-readable",
                "health_path": "/api/health",
                "migrations": True,
                "status": "live",
                "description": "x",
            }
        ]
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_a_hostname_outside_the_domain_is_rejected(schema):
    # Every app is served through the one tunnel, on the one domain. A hostname
    # elsewhere is either a typo or a routing rule that cannot work.
    bad = {
        "apps": [
            {
                "name": "media",
                "hostname": "media.example.com",
                "port": 8000,
                "database": "media",
                "repo": "git@github.com:cg1618-apps/media.git",
                "exposure": "public",
                "health_path": "/api/health",
                "migrations": True,
                "status": "live",
                "description": "x",
            }
        ]
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_no_database_is_legal(schema):
    # An app need not have one, and null must survive the string pattern.
    fine = {
        "apps": [
            {
                "name": "apex",
                "hostname": "apex.cg1618.com",
                "port": 8007,
                "database": None,
                "repo": "git@github.com:cg1618-apps/apex.git",
                "exposure": "public",
                "health_path": "/",
                "migrations": True,
                "status": "live",
                "description": "x",
            }
        ]
    }
    jsonschema.validate(instance=fine, schema=schema)


def entry(**overrides):
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
        "description": "x",
    }
    base.update(overrides)
    return base


def test_migrations_is_required(schema):
    # The whole point of the key: an app that says nothing about its schema is
    # an app bin/deploy cannot tell "I have no migrations" from "my hook is
    # missing". Omitting it must fail here rather than be discovered on the box.
    bad = entry()
    del bad["migrations"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance={"apps": [bad]}, schema=schema)


def test_migrations_must_be_a_boolean(schema):
    # The mirror: `true` passes on the same fixture, so a green above means the
    # required-key rule did the refusing rather than something incidental.
    jsonschema.validate(instance={"apps": [entry(migrations=True)]}, schema=schema)
    jsonschema.validate(instance={"apps": [entry(migrations=False)]}, schema=schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance={"apps": [entry(migrations="yes")]}, schema=schema)


def test_every_registered_app_declares_migrations(registry):
    for app in registry["apps"]:
        assert isinstance(app["migrations"], bool), app["name"]


def test_path_is_optional(schema):
    # Almost every app's checkout is at <apps dir>/<name>. The key exists for
    # the one that predates the layout.
    jsonschema.validate(instance={"apps": [entry()]}, schema=schema)
    jsonschema.validate(
        instance={"apps": [entry(path="~/anime_site")]}, schema=schema
    )
    jsonschema.validate(instance={"apps": [entry(path="/srv/media")]}, schema=schema)


def test_a_path_must_be_absolute_or_home_relative(schema):
    # A relative path would be resolved against whatever directory the deploy
    # script happens to be in, which is the app's own checkout by then.
    for bad in ("anime_site", "./anime_site", "~anime_site"):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance={"apps": [entry(path=bad)]}, schema=schema)


def test_a_path_may_not_contain_whitespace(schema):
    # bin/deploy, bin/health and bin/rollback read the registry's answer as
    # whitespace-separated fields. The schema is what makes that safe.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"apps": [entry(path="/srv/my app")]}, schema=schema
        )


def test_the_one_app_that_needs_a_path_has_one(registry):
    # The media tracker's checkout on the box is ~/anime_site, and that fact
    # has to live somewhere a caller cannot contradict.
    by_name = {app["name"]: app for app in registry["apps"]}
    assert by_name["media"]["path"] == "~/anime_site"
    for name, app in by_name.items():
        if name != "media":
            assert "path" not in app, name


def _entry(**overrides):
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
        "description": "x",
    }
    base.update(overrides)
    return {"apps": [base]}


def test_gated_paths_is_optional(schema):
    # Every app but food has no write prefix to declare, so absence has to
    # stay valid - and this is the mirror that keeps the three below honest.
    jsonschema.validate(instance=_entry(), schema=schema)


def test_a_gated_path_must_be_a_path(schema):
    # The schema carries the shape; bin/validate_apps.py carries which app may
    # hold the key at all.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=_entry(gated_paths=["api/edit"]), schema=schema)


def test_a_gated_path_may_not_repeat(schema):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=_entry(gated_paths=["/api/edit", "/api/edit"]), schema=schema
        )


def test_an_empty_gated_paths_is_rejected(schema):
    # An empty list is not "no write surface" - that is absence. A list that
    # is present and empty reads as a declaration and probes nothing.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=_entry(gated_paths=[]), schema=schema)

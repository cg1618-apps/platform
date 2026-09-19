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

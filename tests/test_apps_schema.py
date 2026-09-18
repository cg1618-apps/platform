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
                "status": "live",
                "description": "x",
            }
        ]
    }
    jsonschema.validate(instance=fine, schema=schema)

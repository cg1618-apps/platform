"""The ingress is derived from the registry, never hand-edited.

This file carries a guard that used to live in the media tracker's own suite
(tests/unit/test_prod_compose.py), where it was the only thing standing between
journal.cg1618.com and a routing rule nobody decided to add. Moving the ingress
here without moving the guard would have quietly deleted that protection.
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

from generate_ingress import render  # noqa: E402

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


def test_the_committed_file_matches_the_registry():
    committed = (ROOT / "cloudflared" / "config.yml").read_text(encoding="utf-8")
    assert committed == render(REGISTRY)


def test_every_app_is_routed_to_its_own_service():
    out = yaml.safe_load(render(REGISTRY))
    rules = {r["hostname"]: r["service"] for r in out["ingress"] if "hostname" in r}
    assert rules["media.cg1618.com"] == "http://media-app:8000"


def test_the_catch_all_is_last():
    # cloudflared refuses to start without it, and it must be the final rule.
    out = yaml.safe_load(render(REGISTRY))
    assert out["ingress"][-1] == {"service": "http_status:404"}
    assert all("hostname" in r for r in out["ingress"][:-1])


def test_a_lan_only_app_is_not_routed():
    # The tunnel IS the public path, so "lan-only" is implemented by the
    # absence of a rule. This is the refusal that matters most here, and it
    # needs a registry that actually contains such an app - apps.yml has none.
    registry = {"apps": [
        app(),
        app(name="money", hostname="money.cg1618.com", port=8001,
            database="money", repo="git@github.com:cg1618-apps/money.git",
            exposure="lan-only", health_path="/health", status="live"),
    ]}
    hostnames = [r.get("hostname") for r in yaml.safe_load(render(registry))["ingress"]]
    assert "media.cg1618.com" in hostnames
    assert "money.cg1618.com" not in hostnames


def test_a_cloudflare_access_app_is_routed_and_marked():
    # The mirror of the case above, on the same shape of fixture: Access is
    # enforced by Cloudflare in front of the tunnel, so the rule does exist -
    # but it must be visibly different in the file a person reads.
    registry = {"apps": [
        app(name="journal", hostname="journal.cg1618.com", port=8002,
            database="journal", repo="git@github.com:cg1618-apps/journal.git",
            exposure="cloudflare-access", health_path="/health", status="live"),
    ]}
    rendered = render(registry)
    hostnames = [r.get("hostname") for r in yaml.safe_load(rendered)["ingress"]]
    assert "journal.cg1618.com" in hostnames
    assert "cloudflare-access" in rendered


def test_the_rendered_file_is_valid_yaml_with_the_credentials_path():
    out = yaml.safe_load(render(REGISTRY))
    assert out["credentials-file"] == "/etc/cloudflared/credentials.json"


def test_a_planned_app_is_not_routed():
    # An entry reserves a hostname, a port and a database the moment an app is
    # planned - that is what stops a second app taking them - but nothing is
    # serving it. A rule would publish a hostname that answers 502, which is
    # worse than one that does not resolve.
    registry = {"apps": [app(name="food", hostname="food.cg1618.com", port=8001,
                             database="food",
                             repo="git@github.com:cg1618-apps/food.git",
                             status="planned")]}
    hostnames = [r.get("hostname") for r in yaml.safe_load(render(registry))["ingress"]]
    assert "food.cg1618.com" not in hostnames


def test_the_apex_is_routed_even_though_it_is_not_in_the_registry():
    # The apex page is infrastructure - a rendering of apps.yml - so it has no
    # entry of its own, and the rule is emitted regardless of what the registry
    # holds.
    out = yaml.safe_load(render({"apps": [app()]}))
    rules = {r["hostname"]: r["service"] for r in out["ingress"] if "hostname" in r}
    assert rules["cg1618.com"] == "http://apex:8007"


def test_ssh_is_routed_to_the_host_even_though_it_is_not_in_the_registry():
    # SSH to the box is infrastructure like the apex: no entry of its own,
    # emitted regardless of the registry, and routed to the HOST's sshd
    # rather than to a service on the cg1618 network.
    out = yaml.safe_load(render({"apps": []}))
    rules = {r["hostname"]: r["service"] for r in out["ingress"] if "hostname" in r}
    assert rules["ssh.cg1618.com"] == "ssh://host.docker.internal:22"

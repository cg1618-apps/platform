"""docker-compose.dev-logs.yml: the collector on a laptop, not on the box.

Two of these assertions are about something that would be expensive rather than
annoying, and they are the reason this file exists at all: a development machine
must never start the tunnel, and it must never start the shared PostgreSQL.

The rest guard drift. A second copy of the Loki, Alloy and Grafana
configuration would diverge from the box's, and the copy that diverged would be
the one nobody reads until a query behaves differently in production.
"""

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "docker-compose.dev-logs.yml"
PROD = ROOT / "docker-compose.prod.yml"


@pytest.fixture(scope="module")
def dev():
    return yaml.safe_load(DEV.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prod():
    return yaml.safe_load(PROD.read_text(encoding="utf-8"))


def test_the_file_exists():
    assert DEV.is_file(), f"{DEV.name} is missing; dev-logs.ps1 cannot run without it"


def test_it_runs_the_collector_and_nothing_else(dev):
    assert set(dev["services"]) == {"loki", "alloy", "grafana"}


def test_it_never_starts_the_tunnel(dev):
    """The expensive one.

    `cloudflared` here would connect a SECOND tunnel using the box's
    credentials. Cloudflare load-balances a tunnel's connections across its
    replicas, so a share of production traffic would start arriving at whoever
    ran this and be answered by whatever their laptop happened to be serving.

    Nothing about that announces itself: the local container looks healthy, and
    the box's does too.
    """
    assert "cloudflared" not in dev["services"]


def test_it_never_starts_the_shared_postgres(dev):
    """`db` would bind 5432 against cg1618-dev-db.

    That is the development database every app's dev.ps1 starts and every app's
    tests use,
    and the collision is quiet in the worst way - docs/dev-ports.md describes
    the shape, where a second server on the same port shadows the first and the
    app talks to an empty database while reporting success.
    """
    assert "db" not in dev["services"]


def test_the_project_name_is_pinned_and_is_not_the_production_one(dev):
    """Compose derives a project name from the DIRECTORY.

    Unpinned, this file and docker-compose.prod.yml are both the project
    `cg1618` in this checkout - so bringing the production file up locally would
    adopt and recreate these three containers, and a `docker compose -f
    docker-compose.prod.yml down` would DELETE them, because compose removes
    everything in the project rather than only the services in the file it was
    handed.
    """
    assert dev.get("name"), "no top-level name:; the project falls back to the directory"
    assert dev["name"] != "cg1618"


def test_nothing_is_published_beyond_loopback(dev):
    """A laptop joins other networks.

    Neither Loki nor Grafana authenticates anything worth the name here, so a
    published port on 0.0.0.0 is an open log reader on whatever wifi this
    machine is next attached to.
    """
    published = [
        port
        for service in dev["services"].values()
        for port in service.get("ports", [])
    ]
    assert published, "nothing is published at all - there would be nothing to view"
    for port in published:
        assert str(port).startswith("127.0.0.1:"), port


def observability_mounts(compose: dict) -> dict[str, list[str]]:
    """{service: every ./observability source it mounts}, sorted.

    A list rather than one string. Grafana mounts two of these - datasources and
    dashboards - and a dict holding only the last one would compare the two
    compose files while silently ignoring the first, which is exactly the kind
    of check that looks thorough and asserts half of what it claims.
    """
    found: dict[str, list[str]] = {}
    for name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            if str(volume).startswith("./observability/"):
                found.setdefault(name, []).append(str(volume))
    return {name: sorted(mounts) for name, mounts in found.items()}


def test_it_mounts_the_same_configuration_the_box_runs(dev, prod):
    """One copy of each config, read by both files.

    A separate dev config is the drift this repository keeps finding: two
    statements of one thing, and the stale one is discovered when production
    behaves differently from the rehearsal.
    """
    dev_mounts = observability_mounts(dev)
    prod_mounts = observability_mounts(prod)
    assert dev_mounts, "the dev file mounts no observability config at all"
    assert dev_mounts == prod_mounts


def test_its_volumes_cannot_be_confused_with_the_box_s(dev, prod):
    """Distinct names, so a local experiment is never restored over real data."""
    assert set(dev["volumes"]) & set(prod["volumes"]) == set()


def test_every_service_caps_its_log_driver(dev):
    """The collector's own containers are containers too.

    Alloy tails every container on the machine, including these three, and
    Loki narrates its own compaction. Uncapped, the collector is the most
    likely thing here to fill a disk.
    """
    for name, service in dev["services"].items():
        logging_config = service.get("logging")
        assert logging_config, f"{name} inherits docker's uncapped json-file default"
        assert logging_config["driver"] == "json-file", name
        assert logging_config["options"]["max-size"] == "10m", name
        assert logging_config["options"]["max-file"] == "5", name


def test_loki_still_has_no_healthcheck(dev):
    """The grafana/loki image is distroless - no shell, and no wget either.

    A healthcheck here does not report Loki as unwell; it reports nothing
    forever while the container sits at `health: starting` and every
    `docker compose ps` reads like a Loki that never came up. It cost two CI
    runs to find that once. dev-logs.ps1 polls /ready from the host instead.
    """
    assert "healthcheck" not in dev["services"]["loki"]


# --- anonymous access is local-only, and the mirror is the point -------------


def grafana_env(compose: dict) -> dict:
    return compose["services"]["grafana"].get("environment") or {}


def test_the_local_grafana_needs_no_login(dev):
    """One click means one click.

    Anonymous access is what makes opening the page the whole interaction. It
    is safe here because both published ports bind 127.0.0.1, so "anyone" means
    "a process on this machine", and Admin rather than Viewer because Explore
    and ad-hoc queries are the entire reason to run it.
    """
    env = grafana_env(dev)
    assert env.get("GF_AUTH_ANONYMOUS_ENABLED") == "true"
    assert env.get("GF_AUTH_ANONYMOUS_ORG_ROLE") == "Admin"


def test_production_grafana_is_never_anonymous(prod):
    """The mirror, and it is worth more than the test above it.

    `logs.cg1618.com` can read every application's logs. Anonymous access there
    would mean Cloudflare Access is the only gate on all of it - and the
    failure this box has actually had is a DNS record reaching it with no
    Access application behind it, which looks identical to a working one from
    everywhere except the open internet.

    The dev file carries these keys with a comment saying not to copy them.
    This is that comment made mechanical, because a comment does not fail a
    pull request.
    """
    env = grafana_env(prod)
    assert "GF_AUTH_ANONYMOUS_ENABLED" not in env
    assert "GF_AUTH_ANONYMOUS_ORG_ROLE" not in env


def test_production_still_refuses_to_start_without_a_real_password(prod):
    """`:?`, not a default.

    With a default, an unset variable leaves Grafana on its built-in
    admin/admin and the container comes up looking entirely healthy. Failing to
    start is the correct end of that, and the dev file's default must not have
    been copied back.
    """
    password = grafana_env(prod)["GF_SECURITY_ADMIN_PASSWORD"]
    assert ":?" in password, password


# --- the one-click wrapper --------------------------------------------------

DEV_CMD = ROOT / "dev.cmd"


def test_the_one_click_wrapper_exists_and_only_delegates():
    """dev.cmd holds no logic, and that is the assertion.

    It exists because Explorer runs a .cmd on a double-click and will not run a
    .ps1, and because an unsigned script needs -ExecutionPolicy Bypass. Logic
    duplicated into it would be logic that the PowerShell script's readers
    never see.
    """
    assert DEV_CMD.is_file()
    body = DEV_CMD.read_text(encoding="utf-8")
    assert "dev-logs.ps1" in body
    assert "-ExecutionPolicy Bypass" in body
    # Arguments pass through, or `dev.cmd -Down` would silently START the stack.
    assert "%*" in body
    # Held open on failure: launched from Explorer the window closes instantly
    # and takes the only explanation with it.
    assert "pause" in body


# --- provisioned datasource and dashboards ----------------------------------

DATASOURCES = ROOT / "observability" / "grafana" / "datasources"
DASHBOARDS = ROOT / "observability" / "grafana" / "dashboards"


def test_the_datasource_uid_is_pinned():
    """Otherwise Grafana generates one per instance.

    A provisioned dashboard names its datasource by uid. Unpinned, the uid on
    the laptop and the uid on the box differ, so the same dashboard file works
    in one place and fails in the other with "datasource not found" - which
    reads as a broken dashboard rather than a broken reference.
    """
    loki = yaml.safe_load((DATASOURCES / "loki.yml").read_text(encoding="utf-8"))
    assert loki["datasources"][0]["uid"] == "loki"


def test_there_is_a_dashboard_provider():
    provider = yaml.safe_load((DASHBOARDS / "dashboards.yml").read_text(encoding="utf-8"))
    entry = provider["providers"][0]
    assert entry["type"] == "file"
    assert entry["options"]["path"] == "/etc/grafana/provisioning/dashboards"
    # Read-only in the UI: a dashboard is a question worth keeping, and one
    # edited in the browser lives only in that Grafana's database.
    assert entry["allowUiUpdates"] is False


def loki_uids(node, found: set[str]) -> set[str]:
    """Every datasource uid a dashboard names, however deeply nested.

    Defined at module level rather than inside the loop below: a closure over a
    per-iteration variable is the B023 bug ruff refuses, and it would have made
    every dashboard after the first assert against the first one's set.
    """
    if isinstance(node, dict):
        if node.get("type") == "loki" and "uid" in node:
            found.add(node["uid"])
        for value in node.values():
            loki_uids(value, found)
    elif isinstance(node, list):
        for value in node:
            loki_uids(value, found)
    return found


def test_every_dashboard_references_the_pinned_datasource():
    """A dashboard naming any other uid renders empty panels on the other machine."""
    dashboards = sorted(DASHBOARDS.glob("*.json"))
    assert dashboards, "no dashboards at all - this test would pass vacuously"
    for path in dashboards:
        blob = json.loads(path.read_text(encoding="utf-8"))
        uids = loki_uids(blob, set())
        assert uids == {"loki"}, f"{path.name} references {uids}"


def test_every_dashboard_panel_has_a_description():
    """A panel whose title is its only explanation is a panel nobody trusts.

    The descriptions are where "what is this actually counting" lives - including
    that the error panels are a TEXT match today and over-count.
    """
    for path in sorted(DASHBOARDS.glob("*.json")):
        blob = json.loads(path.read_text(encoding="utf-8"))
        assert blob["panels"], f"{path.name} has no panels"
        for panel in blob["panels"]:
            assert panel.get("description", "").strip(), f"{path.name}: {panel['title']}"

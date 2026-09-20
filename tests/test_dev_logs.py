"""docker-compose.dev-logs.yml: the collector on a laptop, not on the box.

Two of these assertions are about something that would be expensive rather than
annoying, and they are the reason this file exists at all: a development machine
must never start the tunnel, and it must never start the shared PostgreSQL.

The rest guard drift. A second copy of the Loki, Alloy and Grafana
configuration would diverge from the box's, and the copy that diverged would be
the one nobody reads until a query behaves differently in production.
"""

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
    """`db` would bind 5432 against anime_site_postgres_db.

    That container is what every app's dev.ps1 starts and every app's tests use,
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


def observability_mounts(compose: dict) -> dict[str, str]:
    """{service: the ./observability source it mounts}, for services that do."""
    found = {}
    for name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            if str(volume).startswith("./observability/"):
                found[name] = str(volume)
    return found


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

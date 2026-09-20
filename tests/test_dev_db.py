"""docker-compose.dev-db.yml: the development database, and who cannot touch it.

This file exists because the database used to live in media's compose project,
where `docker compose down` in any media tree removed the server every other app
was using. Most of what follows asserts that the new arrangement cannot be
walked back into that one by accident.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEV_DB = ROOT / "docker-compose.dev-db.yml"
PROD = ROOT / "docker-compose.prod.yml"
DEV_LOGS = ROOT / "docker-compose.dev-logs.yml"


@pytest.fixture(scope="module")
def dev_db():
    return yaml.safe_load(DEV_DB.read_text(encoding="utf-8"))


def test_the_file_exists():
    assert DEV_DB.is_file()


def test_it_is_a_project_of_its_own(dev_db):
    """The whole point of the move.

    Compose removes everything in a PROJECT, not only the services named in the
    file it was handed. Sharing a project name with the production file or with
    the collector would put this database back inside somebody else's blast
    radius - which is the defect it was moved out of.
    """
    prod = yaml.safe_load(PROD.read_text(encoding="utf-8"))
    dev_logs = yaml.safe_load(DEV_LOGS.read_text(encoding="utf-8"))

    assert dev_db["name"] == "cg1618-dev-db"
    assert dev_db["name"] != dev_logs.get("name")
    # The production file pins no top-level name; in this checkout it takes the
    # directory, which is `cg1618`. Either way it must not be ours.
    assert dev_db["name"] != prod.get("name", "cg1618")


def test_it_holds_one_service_and_that_service_is_the_database(dev_db):
    assert set(dev_db["services"]) == {"db"}


def test_the_container_name_is_pinned(dev_db):
    """Every app's dev.ps1 names it, and a compose-generated name would move."""
    assert dev_db["services"]["db"]["container_name"] == "cg1618-dev-db"


def test_the_volume_name_is_explicit_and_is_not_the_box_s(dev_db):
    """A volume left to the project prefix is a volume nobody can find.

    And it must not collide with production's: `cg1618_pgdata` on the box holds
    live data, and a name close enough to confuse is a restore into the wrong
    one at the worst moment.
    """
    prod = yaml.safe_load(PROD.read_text(encoding="utf-8"))
    assert dev_db["volumes"]["pgdata"]["name"] == "cg1618_dev_pgdata"
    assert "cg1618_dev_pgdata" not in prod["volumes"]


def test_it_listens_on_loopback_only(dev_db):
    """media's compose published "5432:5432" - every network this laptop joins.

    The apps connect over loopback, so nothing needs the wider bind, and a
    development database with the superuser's password in it is not something to
    offer a cafe.
    """
    ports = dev_db["services"]["db"]["ports"]
    assert ports == ["127.0.0.1:5432:5432"], ports


def test_the_credentials_are_required_rather_than_defaulted(dev_db):
    """`:?`, so an unset variable fails at `compose up` naming the variable.

    With a default, postgres would refuse to initialise inside the entrypoint
    instead, which is the same outcome reported worse.
    """
    env = dev_db["services"]["db"]["environment"]
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        assert ":?" in env[key], key


def test_it_caps_its_log_driver(dev_db):
    logging_config = dev_db["services"]["db"]["logging"]
    assert logging_config["driver"] == "json-file"
    assert logging_config["options"]["max-size"] == "10m"
    assert logging_config["options"]["max-file"] == "5"


def test_it_does_not_restart_something_you_deliberately_stopped(dev_db):
    """`always` restarts a stopped container when Docker Desktop next starts."""
    assert dev_db["services"]["db"]["restart"] == "unless-stopped"


# --- the wrapper ------------------------------------------------------------

DEV_DB_CMD = ROOT / "dev-db.cmd"
DEV_DB_PS1 = ROOT / "dev-db.ps1"


def test_the_wrapper_exists_and_only_delegates():
    assert DEV_DB_CMD.is_file()
    body = DEV_DB_CMD.read_text(encoding="utf-8")
    assert "dev-db.ps1" in body
    assert "-ExecutionPolicy Bypass" in body
    assert "%*" in body
    assert "pause" in body


def test_the_script_never_removes_the_volume():
    """`compose down -v` here is four apps' development data.

    The script offers -Down and deliberately offers nothing that passes -v. A
    -Clean switch like the collector's would be one keystroke from a day of
    restoring dumps, so it does not exist.
    """
    body = DEV_DB_PS1.read_text(encoding="utf-8")
    assert "down -v" not in body
    assert "-Clean" not in body


def test_the_migration_refuses_to_overwrite_a_populated_target():
    """Running -Migrate twice must not silently replace a live database."""
    body = DEV_DB_PS1.read_text(encoding="utf-8")
    assert "PG_VERSION" in body, "no emptiness check on the target volume"
    assert "-Force" in body, "no explicit override, so the check cannot be passed deliberately"


def test_the_migration_stops_the_old_container_first():
    """Copying a data directory out from under a live postgres is a torn snapshot.

    It usually starts afterwards, and is subtly wrong rather than obviously
    broken - which is the worst of both.
    """
    body = DEV_DB_PS1.read_text(encoding="utf-8")
    assert "docker stop anime_site_postgres_db" in body


def test_the_old_volume_is_only_ever_read():
    """It is the rollback. Nothing here may write to or remove it."""
    body = DEV_DB_PS1.read_text(encoding="utf-8")
    # The mount is written through $oldVolume rather than the literal, so assert
    # both halves: that the variable names the old volume, and that every mount
    # of it is read-only.
    assert "$oldVolume = 'anime_site_postgres_anime_data'" in body
    assert "${oldVolume}:/from:ro" in body
    assert "volume rm" not in body

"""bin/provision's invariants: the ones that would leak or destroy.

It needs a live PostgreSQL to run for real, which CI does not have, so what is
checked here is the shape of the commands it builds. That is worth checking
precisely because the failures it guards against are silent ones.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "bin" / "provision"


def code() -> str:
    """The script with comment lines removed.

    The comments here explain what the script does NOT do - "never passed as a
    command argument", "there is deliberately no un-provision" - so a search of
    the raw text finds the prose that means the opposite of the match.
    """
    lines = PROVISION.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def test_it_fails_fast():
    # Without -e a failed CREATE ROLE is stepped past and the script goes on to
    # write credentials into a .env for a role that does not exist.
    assert "set -euo pipefail" in PROVISION.read_text(encoding="utf-8")


def test_the_password_is_never_an_argument_to_psql():
    # argv is world-readable in `ps` for as long as the command runs. The SQL
    # carrying the password is piped in on stdin instead.
    body = code()
    assert "--password=" not in body
    assert "-c \"CREATE ROLE" not in body
    assert "-c \"ALTER ROLE" not in body


def test_the_generated_password_goes_straight_to_a_file():
    for line in code().splitlines():
        if "openssl rand" in line:
            assert ">" in line, line
            assert "echo" not in line, line


def test_the_secret_file_is_private_and_removed():
    body = code()
    assert 'chmod 600 "${secret}"' in body
    assert "trap 'rm -f" in body


def test_the_written_env_file_is_private():
    # It now holds a password. 644 would publish it to every user on the box.
    assert 'chmod 600 "${ENV_FILE}"' in code()


def test_it_refuses_an_app_that_is_not_registered():
    assert "is not in apps.yml" in PROVISION.read_text(encoding="utf-8")


def test_it_refuses_an_app_with_no_database():
    assert "declares no database" in PROVISION.read_text(encoding="utf-8")


def test_it_refuses_to_replace_an_existing_role_without_being_told():
    # Rotating silently would leave the app holding the old password in its
    # .env until someone restarts it - which reads as a database outage rather
    # than as a provisioning mistake.
    body = code()
    assert "--rotate" in body
    assert "already exists" in body


def test_it_never_drops_anything():
    lowered = code().lower()
    assert "drop database" not in lowered
    assert "drop role" not in lowered
    assert "drop schema" not in lowered


def test_it_clears_the_compose_project_name():
    # The lesson from the stack split: an app's .env exports
    # COMPOSE_PROJECT_NAME, and an exported variable beats the .env beside this
    # compose file. Nothing here sources an app's .env today, but this script is
    # the one most likely to be copied into something that does.
    assert "env -u COMPOSE_PROJECT_NAME docker compose" in code()


def test_it_rewrites_exactly_three_keys_and_not_the_connection_string():
    # The app's own DATABASE_URL may carry a driver, a schema or options this
    # script cannot guess, so it is left alone and the closing message says so.
    # What matters is the set of keys the rewrite touches - not whether the
    # string appears in the file, which it does, in a message.
    body = code()
    wanted = body[body.index("wanted = {") : body.index("lines, seen")]
    assert '"POSTGRES_USER"' in wanted
    assert '"POSTGRES_PASSWORD"' in wanted
    assert '"POSTGRES_DB"' in wanted
    assert "DATABASE_URL" not in wanted

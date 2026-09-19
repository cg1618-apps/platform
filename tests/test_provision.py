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


def test_it_arms_the_deploy_approval_gate():
    # The `production` environment is the one item of the app contract that
    # exists only as a GitHub setting. Referencing an environment that does
    # not exist creates it with no protection rules and runs the job, so an
    # app nobody armed would deploy a migration unattended - with the gate
    # present in the workflow and meaning nothing.
    body = code()
    assert "environments/production" in body
    assert "reviewers[][type]=User" in body


def test_a_missing_gh_prints_the_command_rather_than_failing():
    # provision's job is the database. Aborting after the role, the database
    # and the .env are written would report failure over work that succeeded,
    # on a box that may have no gh and no login.
    body = code()
    assert "command -v gh" in body
    assert "arm_env_cmd" in body
    for line in body.splitlines():
        if "environments/production" in line and "gh api -X PUT" in line:
            assert not line.strip().startswith("exit"), line


def test_the_env_file_default_honours_the_registry_path():
    # This script read the registry for the database name and GUESSED the
    # directory, so `provision media` looked in ~/media/.env for an app whose
    # checkout is ~/anime_site. The other three scripts resolve it the same
    # way; this was the one that did not.
    body = code()
    assert '"path"' in body
    assert "REG_PATH" in body
    assert 'ENV_FILE="${APP_DIR}/.env"' in body


def test_the_environment_flags_are_typed():
    # -f sends every value as a JSON string. prevent_self_review is a typed
    # boolean, so -f earns a 422 - and provision would then print the same
    # broken command for the owner to paste.
    for line in code().splitlines():
        if "prevent_self_review" in line:
            assert "-F 'prevent_self_review" in line, line
            assert "-f 'prevent_self_review" not in line, line


def test_the_registry_path_is_expanded_the_same_way_as_the_other_scripts():
    # Same mechanism, same reasoning: strip a literal "~/" and prepend HOME
    # when that removed something. Four copies of one idea, and a fifth
    # spelling would be a fifth thing to verify.
    body = code()
    assert r'stripped="${REG_PATH#\~/}"' in body
    assert 'APP_DIR="${HOME}/${stripped}"' in body


def test_it_refuses_a_checkout_that_is_not_on_main():
    """A plain `git clone` gives you dev here, not main.

    `dev` is the default branch of every app repository, so cloning an app
    onto the box leaves it on the branch `bin/deploy` refuses. Nothing
    notices until a deploy, and by then it has cost a production approval:
    food's first deploy was approved, then refused with "On 'dev', not main".
    Provisioning is where that is cheap to find.
    """
    body = code()
    assert "rev-parse --abbrev-ref HEAD" in body
    assert 'checkout main' in body

    # The check must run before the password is generated: refusing after
    # would leave a role created with a password nothing has recorded.
    assert body.index("rev-parse --abbrev-ref HEAD") < body.index("openssl rand")

"""bin/deploy, bin/health and bin/rollback: the invariants that cost something.

These three scripts need a box - a live PostgreSQL, a built image, a checkout
of the app being deployed - so what is checked here is the shape of what they
build and refuse, the same way tests/test_provision.py checks bin/provision.

Every assertion below stands for a failure that happened once on the box while
this logic lived in one application's deploy/ directory. Generalising it must
not quietly drop any of them.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "bin" / "deploy"
HEALTH = ROOT / "bin" / "health"
ROLLBACK = ROOT / "bin" / "rollback"
SCRIPTS = (DEPLOY, HEALTH, ROLLBACK)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code(path: Path) -> str:
    """The script with comment lines removed.

    The comments say what the scripts do NOT do - "never restores data", "not
    optional" - so a search of the raw text keeps finding the prose that means
    the opposite of the match.
    """
    lines = text(path).splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def command_lines(path: Path, needle: str) -> list[str]:
    return [line for line in code(path).splitlines() if needle in line]


# --- the basics -------------------------------------------------------------


def test_they_all_exist_and_fail_fast():
    for script in SCRIPTS:
        body = text(script)
        assert body.startswith("#!/usr/bin/env bash"), script
        # Without -e a failed dump is stepped past and the deploy continues
        # with no rollback option behind it.
        assert "set -euo pipefail" in body, script


def usable_bash() -> str | None:
    """A bash that can actually execute, or None.

    `shutil.which` is not enough on Windows: it finds WSL's stub, which is on
    PATH whether or not a distribution is installed and fails with an execvpe
    error rather than running anything.
    """
    exe = shutil.which("bash")
    if exe is None:
        return None
    try:
        probe = subprocess.run([exe, "-c", "exit 0"], capture_output=True, check=False)
    except OSError:
        return None
    return exe if probe.returncode == 0 else None


def test_they_parse():
    # shellcheck runs in CI; `bash -n` is the check that runs anywhere bash
    # does, and catches the unbalanced quote that would otherwise reach the box.
    exe = usable_bash()
    if exe is None:
        pytest.skip("no working bash on this machine")
    for script in SCRIPTS:
        subprocess.run([exe, "-n", str(script)], check=True)


def test_they_are_committed_executable():
    # A shell script committed 100644 is a shell script the box cannot run.
    for script in SCRIPTS:
        rel = script.relative_to(ROOT).as_posix()
        out = subprocess.run(
            ["git", "ls-tree", "HEAD", "--", rel],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if not out:
            pytest.skip(f"{rel} is not committed yet")
        assert out.split()[0] == "100755", out


# --- the exit codes ---------------------------------------------------------


def test_deploy_exits_two_when_unhealthy_and_one_when_it_refuses():
    body = text(DEPLOY)
    assert "exit 2" in body
    # The refusals: wrong branch, no .env, an unapproved migration.
    assert body.count("exit 1") >= 3


def test_exit_two_belongs_to_the_health_check_and_nothing_else():
    # The workflow reads the distinction to decide whether rolling back is
    # correct. A second exit 2 anywhere else would roll back a deploy that
    # never touched the box.
    body = code(DEPLOY)
    assert body.count("exit 2") == 1
    tail = body[body.index("exit 2") - 400 : body.index("exit 2")]
    assert "bin/health" in tail or "health" in tail


def test_rollback_freezes_rather_than_guessing():
    body = code(ROLLBACK)
    assert "exit 3" in body
    # It reverses schema and swaps the image. Restoring data automatically
    # would discard every write since the dump.
    assert "pg_restore" not in body


# --- the registry is the source of truth ------------------------------------


def test_health_path_comes_from_the_registry():
    body = text(HEALTH)
    assert "/api/health" not in body, "health_path must come from apps.yml"
    assert "health_path" in body


def test_every_script_validates_the_app_against_the_registry():
    for script in SCRIPTS:
        body = text(script)
        assert "apps.yml" in body, script
        assert "is not in apps.yml" in body, script


def test_the_database_name_comes_from_the_registry():
    # Not from the app's .env: a typo there would dump a database no generated
    # file knows about, and the dump would look fine.
    assert "database" in code(DEPLOY)


def test_nothing_is_hard_coded_to_one_app():
    for script in SCRIPTS:
        body = text(script)
        assert "media-app" not in body, script
        assert "anime_site" not in code(script), script


def test_the_app_checkout_is_resolvable_and_overridable():
    # The media tracker's checkout on the box is ~/anime_site, not ~/media.
    for script in SCRIPTS:
        body = code(script)
        assert "APPS_DIR" in body, script
        assert "--app-dir" in body, script


# --- the compose split ------------------------------------------------------


def test_database_calls_clear_the_compose_project_name():
    # These scripts source the app's .env with `set -a`, which EXPORTS
    # COMPOSE_PROJECT_NAME - and an exported variable beats the .env beside the
    # platform's compose file. Without this, compose looks for service `db` in
    # the app's project and reports it missing while it runs one container away.
    body = code(DEPLOY)
    assert 'env -u COMPOSE_PROJECT_NAME docker compose -f "${PLATFORM_DIR}/docker-compose.prod.yml"' in body
    for line in command_lines(DEPLOY, "exec -T db"):
        assert "DB_COMPOSE" in line, line


def test_calls_that_run_the_apps_image_keep_the_project_name():
    # The other half: `up`, `ps` and the health probe mean the APP's compose
    # project, and clearing the name there would aim them at the platform's.
    for script in (DEPLOY, ROLLBACK, HEALTH):
        for needle in ("up -d", "exec -T app", "run --rm"):
            for line in command_lines(script, needle):
                assert "env -u" not in line, line
                assert "DB_COMPOSE" not in line, line


# --- the dump ---------------------------------------------------------------


def test_the_dump_is_refused_when_it_is_empty():
    # A truncated or empty dump is worse than none, because it looks like a
    # rollback option right up until it is needed.
    body = code(DEPLOY)
    assert '[ ! -s "${dump}" ]' in body
    assert "exit 1" in body[body.index('[ ! -s "${dump}" ]') :]
    assert 'rm -f "${dump}"' in body


def test_the_revision_travels_beside_the_dump():
    # Rolling back means checking that revision out before restoring, so it
    # goes next to the dump rather than into someone's head.
    body = code(DEPLOY)
    assert 'git rev-parse HEAD > "${dump}.revision"' in body
    assert '"${dump}.migration"' in body
    assert '"${dump}.revision"' in code(ROLLBACK)


def test_the_prune_keeps_a_few_dumps_and_their_sidecars():
    body = code(DEPLOY)
    assert "KEEP" in body
    assert "tail -n +$((KEEP + 1))" in body
    prune = body[body.index("tail -n +$((KEEP + 1))") :]
    assert ".revision" in prune
    assert ".migration" in prune


# --- migrations are the app's business --------------------------------------


def test_no_migration_tool_is_named_here():
    # The platform asks three questions through deploy/migrations; the answers
    # are Alembic's in one app and something else in the next.
    for script in SCRIPTS:
        assert "alembic" not in text(script).lower(), script


def test_an_app_with_no_migration_hook_is_handled_rather_than_crashing():
    for script in (DEPLOY, ROLLBACK):
        body = code(script)
        assert '-x "${MIGRATIONS}"' in body, script
    # deploy skips the sidecar and the approval gate; rollback goes straight
    # from the image swap to freezing.
    assert "no migrations" in text(DEPLOY).lower()
    assert "no migrations" in text(ROLLBACK).lower()


def test_deploy_re_checks_arriving_migrations_against_this_box():
    # The workflow classifies a deploy from one push range. If the runner was
    # offline across two merges that range misses the earlier one, so the box's
    # own HEAD is re-checked here.
    body = code(DEPLOY)
    assert "MIGRATION_APPROVED" in body
    assert '"${MIGRATIONS}" added' in body
    gate = body[body.index("MIGRATION_APPROVED") :]
    assert "exit 1" in gate


def test_rollback_downgrades_through_the_hook_and_freezes_if_it_refuses():
    body = code(ROLLBACK)
    assert '"${MIGRATIONS}" downgrade' in body
    line = command_lines(ROLLBACK, '"${MIGRATIONS}" downgrade')[0]
    assert "freeze" in line, line


# --- the branch check -------------------------------------------------------


def test_the_branch_check_keeps_its_detached_head_exception():
    # Refusing a detached HEAD outright means one rollback disables automatic
    # deploys permanently and silently - observed on the box.
    body = code(DEPLOY)
    assert "git merge-base --is-ancestor HEAD origin/main" in body
    assert "Refusing to deploy" in body
    assert "git checkout --quiet main" in body


def test_the_outgoing_image_is_tagged_before_the_pull():
    body = code(DEPLOY)
    assert '${APP}-app:previous' in body
    assert body.index("docker tag") < body.index("git pull --ff-only")
    assert '${APP}-app:previous' in code(ROLLBACK)


# --- the health probe -------------------------------------------------------


def test_health_probes_from_inside_the_container():
    # Going out to the hostname and back would make Cloudflare's availability
    # part of the deploy's success condition, and the tunnel is the one
    # component a deploy cannot fix.
    body = code(HEALTH)
    assert "exec -T app" in body
    assert "cg1618.com" not in body
    assert "hostname" not in body


def test_health_prints_the_logs_when_it_gives_up():
    # The caller is a workflow step nobody is watching; without this the
    # failure arrives as a bare non-zero exit.
    body = code(HEALTH)
    assert "logs --tail" in body
    assert "exit 1" in body

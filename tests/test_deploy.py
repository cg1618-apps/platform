"""bin/deploy, bin/health and bin/rollback: the invariants that cost something.

These three scripts need a box - a live PostgreSQL, a built image, a checkout
of the app being deployed - so what is checked here is the shape of what they
build and refuse, the same way tests/test_provision.py checks bin/provision.

Every assertion below stands for a failure that happened once on the box while
this logic lived in one application's deploy/ directory. Generalising it must
not quietly drop any of them.
"""

import re
import shutil
import subprocess
import tempfile
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
    for script in shell_scripts():
        subprocess.run([exe, "-n", str(script)], check=True)


SHEBANGS = ("#!/usr/bin/env bash", "#!/usr/bin/env sh", "#!/bin/bash", "#!/bin/sh")


def shell_scripts() -> list[Path]:
    """Every shell script in bin/, found by first line the way CI finds them.

    Not the three new ones: covering only those is exactly how bin/provision
    stayed 100644 through the change that added this file.
    """
    found = []
    for path in sorted((ROOT / "bin").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        first = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        if first and first[0].startswith(SHEBANGS):
            found.append(path)
    return found


def test_the_shell_scripts_are_found_at_all():
    # The guard on the guard: a detection that finds nothing passes every
    # assertion below without checking a thing.
    names = {p.name for p in shell_scripts()}
    assert {"deploy", "health", "rollback", "provision"} <= names, names


def test_they_are_committed_executable():
    # A shell script committed 100644 is a shell script the box cannot run,
    # and a lost mode bit is also what makes an app's migration hook vanish
    # silently - which is why this covers EVERY script in bin/ rather than the
    # three this file was written for.
    for script in shell_scripts():
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


def test_exit_two_begins_at_the_pull_and_exit_one_ends_there():
    # The workflow reads the distinction to decide whether rolling back is
    # correct, and the pull is where "the deploy ran" begins. Before it,
    # nothing was touched and a rollback would be wrong; after it, `compose up
    # --build` has migrated the database, so a failure is an unhealthy deploy
    # rather than a refusal.
    #
    # The window-and-substring version of this test accepted dead code: a
    # gutted script that exited 1 before ever reaching the health check, with
    # `exit 2` unreachable below it, passed.
    body = code(DEPLOY)
    pull = body.index("git pull --ff-only")

    # Exactly two: the trap armed at the pull, and the explicit one after the
    # health check. A third is an exit 2 somewhere nobody reasoned about.
    assert body.count("exit 2") == 2, body.count("exit 2")
    assert body.index("trap 'exit 2' ERR") > pull

    health = body.index('"${PLATFORM_DIR}/bin/health"')
    assert health > pull
    assert body.rindex("exit 2") > health

    # And nothing refuses after the pull. Telling the workflow "it refused to
    # start, do not roll back" over a database that may have migrated is the
    # wrong side of the contract.
    assert "exit 1" not in body[pull:], body[pull:]


def test_everything_that_makes_a_rollback_possible_precedes_the_pull():
    # A bin/deploy that never dumped, never checked the dump and never
    # recorded the schema revision passed 23 of the 24 tests this file had.
    # Nothing mentioned pg_dump; nothing asserted the order the script's own
    # docstring calls its purpose.
    body = code(DEPLOY)
    pull = body.index("git pull --ff-only")
    assert body.index("pg_dump") < pull
    assert body.index('[ ! -s "${dump}" ]') < pull
    assert body.index('"${dump}.migration"') < pull
    assert body.index('git rev-parse HEAD > "${dump}.revision"') < pull


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
    # file knows about, and the dump would look fine. Asserting that the word
    # "database" appears somewhere proved none of that.
    body = code(DEPLOY)
    assert "apps.yml" in body
    assert 'entry["database"]' in body, "the value must be read out of apps.yml"
    assert "read -r DB " in body
    dump_line = command_lines(DEPLOY, "pg_dump")[0]
    assert '-d "${DB}"' in dump_line, dump_line
    assert body.index('entry["database"]') < body.index('-d "${DB}"')


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
    expected = (
        "env -u COMPOSE_PROJECT_NAME "
        "-u POSTGRES_USER -u POSTGRES_PASSWORD -u POSTGRES_DB "
        'docker compose -f "${PLATFORM_DIR}/docker-compose.prod.yml"'
    )
    # POSTGRES_* as well as the project name: this script sources the APP's
    # .env with `set -a`, so leaving them exported interpolates the PLATFORM's
    # compose file with one app's credentials.
    assert expected in body
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
    # Narrowly: the probe must not read the app's public hostname out of the
    # registry, nor go out over the network to reach it. The bare word trips
    # on any future comment that merely says "hostname".
    assert '["hostname"]' not in body
    assert "https://" not in body


def test_health_prints_the_logs_when_it_gives_up():
    # The caller is a workflow step nobody is watching; without this the
    # failure arrives as a bare non-zero exit.
    body = code(HEALTH)
    assert "logs --tail" in body
    assert "exit 1" in body


# --- the hook's exit status is not this script's ----------------------------


def test_the_hook_is_never_called_bare():
    """A hook failure must not become the deploy's exit status.

    `psql` exits 2 when its connection to the server goes bad, and a hook that
    pipes psql under `pipefail` passes that straight out. Under `set -e` a bare
    call then exits bin/deploy with 2 - which means "the deploy ran and is
    unhealthy" - having pulled, built and started nothing. The workflow rolls
    back, and a connection blip has manufactured an outage.

    Every call therefore tests its own status: `if !`, or `|| freeze`.
    """
    # An INVOCATION is the path followed by one of the three subcommands.
    # The path also appears in lines that merely handle the file - the deploy
    # writes the incoming revision's hook to it and removes it again - and
    # those are not calls and have no exit status to protect.
    invocation = re.compile(r'"\$\{MIGRATIONS\}"\s+(current|added|downgrade)\b')

    seen = 0
    for script in (DEPLOY, ROLLBACK):
        for line in command_lines(script, '"${MIGRATIONS}"'):
            if not invocation.search(line):
                continue
            seen += 1
            guarded = line.strip().startswith("if ! ") or "|| freeze" in line
            assert guarded, f"{script.name}: {line.strip()}"

    # Without this the test passes when the pattern above matches nothing -
    # which is exactly what a renamed variable or a reworked hook would do,
    # and the gate would go green having checked no calls at all.
    assert seen >= 3, f"expected to find the hook's calls, found {seen}"
def test_a_failed_added_call_refuses_rather_than_reporting_nothing():
    # "I could not tell" and "there were none" are opposite answers, and the
    # second one deploys an unapproved migration (deploy) or swaps the image
    # back under a migrated schema (rollback).
    assert 'if ! incoming="$("${MIGRATIONS}" added HEAD origin/main)"' in code(DEPLOY)
    assert 'if ! added="$("${MIGRATIONS}" added "${previous_rev}" HEAD)"' in code(ROLLBACK)
    # The masking form is gone, not merely joined by the guarded one.
    assert '" added "${previous_rev}" HEAD || true' not in code(ROLLBACK)


def test_a_failed_current_call_refuses_and_clears_the_dump():
    body = code(DEPLOY)
    assert 'if ! "${MIGRATIONS}" current > "${dump}.migration"' in body
    after = body[body.index('if ! "${MIGRATIONS}" current') :]
    assert 'rm -f "${dump}"' in after.split("fi")[0]


# --- the registry and the repository must agree -----------------------------


def test_both_scripts_read_the_migrations_declaration_from_the_registry():
    # Presence of the hook is an observation; whether the app HAS migrations is
    # a declaration. Before the key existed, a hook that had lost its mode bit
    # was indistinguishable from an app with no schema.
    for script in (DEPLOY, ROLLBACK):
        body = code(script)
        assert '"migrations" not in' in body, script
        assert 'HAS_MIGRATIONS' in body, script
        assert '[ "${HAS_MIGRATIONS}" = "true" ]' in body, script


def test_a_hook_that_is_not_an_executable_file_is_refused():
    # -f as well as -x, because -x is true of a DIRECTORY: that passes the gate
    # and exits 126 on the first call.
    for script in (DEPLOY, ROLLBACK):
        body = code(script)
        assert (
            '[ -e "${MIGRATIONS}" ] && { [ ! -f "${MIGRATIONS}" ] '
            '|| [ ! -x "${MIGRATIONS}" ]; }'
        ) in body, script


def test_declaring_migrations_without_a_runnable_hook_is_refused():
    body = code(DEPLOY)
    assert '[ "${HAS_MIGRATIONS}" = "true" ] && [ ! -x "${MIGRATIONS}" ]' in body
    gate = body[body.index('[ "${HAS_MIGRATIONS}" = "true" ] && [ ! -x') :]
    assert "exit 1" in gate.split("fi")[0]
    # rollback freezes rather than exiting, so the dump is named.
    rb = code(ROLLBACK)
    assert '[ "${HAS_MIGRATIONS}" = "true" ] && [ ! -x "${MIGRATIONS}" ]' in rb
    assert "freeze" in rb[rb.index('[ "${HAS_MIGRATIONS}" = "true" ] && [ ! -x') :].split("fi")[0]


def test_declaring_no_migrations_with_a_hook_present_is_refused():
    # The mirror, and it is not symmetry for its own sake: the registry and the
    # repository disagreeing is a thing a person settles, not a thing a script
    # guesses at.
    for script in (DEPLOY, ROLLBACK):
        body = code(script)
        assert '[ "${HAS_MIGRATIONS}" != "true" ] && [ -e "${MIGRATIONS}" ]' in body, script
    assert "exit 1" in code(DEPLOY)[
        code(DEPLOY).index('[ "${HAS_MIGRATIONS}" != "true" ] && [ -e') :
    ].split("fi")[0]
    assert "freeze" in code(ROLLBACK)[
        code(ROLLBACK).index('[ "${HAS_MIGRATIONS}" != "true" ] && [ -e') :
    ].split("fi")[0]


# --- what the hook is told --------------------------------------------------


def test_platform_dir_is_exported_to_the_hook():
    # The hook reaches back into the platform's compose project to read its own
    # version table. This process is the only one that knows that path
    # authoritatively; a hook left to guess ${HOME}/cg1618 is right until the
    # checkout moves.
    for script in (DEPLOY, ROLLBACK):
        assert "export PLATFORM_DIR" in code(script), script


# --- the arguments ----------------------------------------------------------


def test_a_second_app_argument_is_refused():
    # `deploy media food` deployed food, and read as a deploy of media.
    for script in SCRIPTS:
        body = code(script)
        assert "unexpected argument" in body, script


# --- rollback leaves nothing half-done --------------------------------------


def test_the_missing_dump_freeze_is_reachable():
    """The assignment that finds the dump must not be able to abort the script.

    Under `set -e` with `pipefail`, `dump="$(ls ... | head -1)"` fails when the
    glob matches nothing, so bin/rollback exited 2 before the `[ -z ]` check
    beneath it ever ran. The freeze for the worst case - a rollback wanted with
    nothing to roll back to - had never been reachable.

    Same family as the `added` masking: a failure being taken for an answer,
    except this one is taken for no answer at all.
    """
    body = code(ROLLBACK)
    line = command_lines(ROLLBACK, "pre-deploy-*.dump")[0]
    assert "|| true" in line, line
    # And the check it exists to reach is still below it, and still freezes.
    assert body.index("pre-deploy-*.dump") < body.index('[ -z "${dump}" ]')
    guard = body[body.index('[ -z "${dump}" ]') :]
    assert "freeze" in guard.split("fi")[0]


def test_the_prune_cannot_trigger_a_rollback():
    # It sits under the ERR trap armed at the pull, so a failing `ls` under
    # pipefail would report "unhealthy, roll back" for housekeeping that has
    # nothing to do with whether the deploy is serving.
    body = code(DEPLOY)
    prune = body[body.index("tail -n +$((KEEP + 1))") :]
    assert "|| true" in prune.split("\n\n")[0], prune.split("\n\n")[0]
    assert body.index("trap 'exit 2' ERR") < body.index("tail -n +$((KEEP + 1))")


def test_the_image_swap_freezes_on_failure():
    # A failure between the checkout and the tag leaves the app half-reverted,
    # and the bare form exited 1 without naming the dump a person then needs.
    for needle in ('git checkout --quiet "${previous_rev}"', "docker tag"):
        for line in command_lines(ROLLBACK, needle):
            assert "|| freeze" in line, line


def test_the_checkout_path_comes_from_the_registry_not_from_a_caller():
    # It was a workflow input once, and a caller could then name one app and
    # hand it another's checkout: the database name came from the registry and
    # the code came from the input, so bin/deploy would dump one app and
    # deploy another. Everything these scripts act on is registry-derived now.
    for script in SCRIPTS:
        body = code(script)
        assert '"path"' in body, script
        assert 'REG_PATH' in body, script
        # --app-dir still wins, for running these by hand against a checkout
        # the registry knows nothing about.
        assert body.index("--app-dir") < body.index('[ -z "${APP_DIR}" ]'), script


def test_a_home_relative_registry_path_is_expanded():
    # The shell does not expand a tilde that arrives inside a variable, so a
    # literal "~/anime_site" would become a directory called "~" beside the
    # runner's cwd - and the checkout guard would then say "no checkout at
    # ~/anime_site", which is exactly what the registry says there is.
    #
    # The mechanism, not its spelling: strip a literal "~/" off the front and
    # prepend HOME when that actually removed something. It was a `case` with
    # a quoted "~/" pattern, which shellcheck reads (SC2088) as a tilde
    # somebody expected the shell to expand - the very mistake this avoids.
    for script in SCRIPTS:
        body = code(script)
        assert r'stripped="${REG_PATH#\~/}"' in body, script
        assert '[ "${stripped}" != "${REG_PATH}" ]' in body, script
        assert 'APP_DIR="${HOME}/${stripped}"' in body, script
        # And the other arm: an absolute path is used as it stands.
        assert 'APP_DIR="${REG_PATH}"' in body, script


def test_the_freeze_message_the_workflow_greps_for_is_exactly_that_string():
    # deploy-app.yml's rollback step pulls the dump out of this script's
    # output with `sed -n 's/.*pre-deploy dump: *//p'` so the ::error:: it
    # raises can name it. Rename the message and the annotation degrades to
    # "see the log above" - silently, with every other test still green,
    # in the one situation where a person is being summoned.
    assert "pre-deploy dump: " in text(ROLLBACK)
    workflow = (ROOT / ".github" / "workflows" / "deploy-app.yml").read_text(
        encoding="utf-8"
    )
    assert "pre-deploy dump: " in workflow


# --- the hook comes from the revision being deployed ------------------------


def build_app_checkout(tmp_path: Path, with_hook: bool, mode: int = 0o755) -> Path:
    """An app checkout on main, with an origin whose main is one commit ahead.

    The incoming commit is what `--ci` deploys, and whether IT carries
    deploy/migrations is the question these tests ask. The checkout itself
    never has the hook, which is the state every app is in before its first
    deploy.
    """
    exe = usable_bash()
    assert exe is not None

    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    checkout = tmp_path / "checkout"

    script = f"""
    set -eu
    export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t
    export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
    git init --quiet --bare -b main '{origin.as_posix()}'
    git clone --quiet '{origin.as_posix()}' '{work.as_posix()}'
    cd '{work.as_posix()}'
    git symbolic-ref HEAD refs/heads/main
    echo app > README
    git add README
    git commit --quiet -m first
    git push --quiet origin main
    git clone --quiet '{origin.as_posix()}' '{checkout.as_posix()}'
    """
    if with_hook:
        script += f"""
    mkdir -p deploy
    printf '#!/usr/bin/env bash\necho base\n' > deploy/migrations
    chmod {mode:o} deploy/migrations
    git add deploy/migrations
    git update-index --chmod={'+x' if mode & 0o111 else '-x'} deploy/migrations
    git commit --quiet -m hook
    git push --quiet origin main
    """
    subprocess.run([exe, "-c", script], check=True, capture_output=True)
    return checkout


def run_deploy(checkout: Path) -> subprocess.CompletedProcess:
    exe = usable_bash()
    return subprocess.run(
        [exe, str(DEPLOY), "travel", "--ci", "--app-dir", str(checkout)],
        capture_output=True,
        text=True,
    )


def test_a_first_deploy_reads_the_hook_from_the_incoming_commit():
    """The checkout predates the hook on every app's first deploy.

    The checkout is cloned to provision the app, before a release exists to
    clone from; the hook arrives with the release being deployed. Reading it
    from the checkout refuses that deploy - which is how travel's first
    deploy failed, after its production gate had been approved.
    """
    if usable_bash() is None:
        pytest.skip("no working bash on this machine")
    tmp = Path(tempfile.mkdtemp())
    try:
        checkout = build_app_checkout(tmp, with_hook=True)
        assert not (checkout / "deploy" / "migrations").exists(), (
            "the checkout must NOT have the hook, or this tests nothing"
        )
        result = run_deploy(checkout)
        # It gets past the hook guards and on to the database, which is not
        # running here. What matters is that it did not refuse for a missing
        # hook: that refusal is the defect.
        # Absence of one message is too weak an assertion: it passed
        # while the deploy died one line later with "No such file or
        # directory", because the checkout had no deploy/ directory for
        # the incoming hook to be written into. So assert PROGRESS: it
        # must reach the .env check, which is the next thing a bare
        # test checkout fails on.
        assert "deploy/migrations is not" not in result.stderr, result.stderr
        assert "No such file or directory" not in result.stderr, result.stderr
        assert "No .env in" in result.stderr, result.stdout + result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_it_refuses_when_the_incoming_commit_has_no_hook():
    # The mirror, and the reason the test above proves anything: with the
    # registry declaring migrations and the incoming commit carrying no hook,
    # the deploy must still refuse. Without this, a change that skipped the
    # guard entirely would pass the test above.
    if usable_bash() is None:
        pytest.skip("no working bash on this machine")
    tmp = Path(tempfile.mkdtemp())
    try:
        checkout = build_app_checkout(tmp, with_hook=False)
        result = run_deploy(checkout)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "deploy/migrations is not" in result.stderr, result.stderr
        assert "origin/main" in result.stderr, result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_it_refuses_when_the_incoming_hook_lost_its_mode_bit():
    # This repository has lost that bit four times to a machine with
    # core.fileMode=false, and a hook that cannot execute is indistinguishable
    # from an app with no migrations unless the mode is read from the tree.
    if usable_bash() is None:
        pytest.skip("no working bash on this machine")
    tmp = Path(tempfile.mkdtemp())
    try:
        checkout = build_app_checkout(tmp, with_hook=True, mode=0o644)
        result = run_deploy(checkout)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "100644" in result.stderr, result.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_the_incoming_hook_is_written_beside_the_real_one():
    # The hook finds the app root with `cd "$(dirname "$0")/.."`, so a copy
    # written anywhere but deploy/ would cd to the wrong directory and read
    # the wrong .env - or none at all.
    body = code(DEPLOY)
    assert '"${APP_DIR}/deploy/.migrations-incoming"' in body
    # And it does not survive the run: an executable left in the checkout is
    # picked up by the next thing that globs deploy/.
    assert "rm -f" in body and "EXIT" in body


# --- the box's checkouts are the ones that act ------------------------------


def test_no_single_file_bind_mounts_in_the_production_stack():
    """A file bind mount pins the inode; `git pull` replaces the file.

    The container then serves the old content while the file on disk is
    correct, and nothing on either side says so. It cost an afternoon the day
    travel went live: the apex page on disk linked to travel and the page
    being served still said "planned". A directory mount re-resolves the name
    on every open, so the same pull is picked up.
    """
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    mounts = []
    for line in compose.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ./"):
            continue
        source = stripped[2:].split(":", 1)[0]
        mounts.append(source)

    assert mounts, "found no bind mounts at all - this test would pass vacuously"
    for source in mounts:
        path = ROOT / source[2:]
        assert path.is_dir(), f"{source} is a file bind mount; mount its directory"


def test_no_bind_mount_contains_another():
    """A read-only mount cannot host a mountpoint docker has to create.

    Mounting a directory at /etc/cloudflared while the credentials mount
    lands at /etc/cloudflared/credentials.json means runc must create that
    mountpoint inside a read-only mount. It cannot: the container dies with
    "read-only file system", and for the tunnel that is every hostname on the
    box at once. Making the mountpoint exist is not the fix either - the file
    is a credential and is never committed.

    Siblings, always. This is the test the outage did not have.
    """
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    service = None
    destinations: dict[str, list[str]] = {}
    for line in compose.splitlines():
        if re.match(r"^  [a-z0-9_-]+:$", line):
            service = line.strip().rstrip(":")
        stripped = line.strip()
        if service and stripped.startswith("- ") and ":" in stripped:
            parts = stripped[2:].split(":")
            if len(parts) >= 2 and parts[1].startswith("/"):
                destinations.setdefault(service, []).append(parts[1])

    assert destinations, "found no bind mounts at all - this test would pass vacuously"

    for service, paths in destinations.items():
        for outer in paths:
            for inner in paths:
                if outer == inner:
                    continue
                assert not inner.startswith(outer.rstrip("/") + "/"), (
                    f"{service}: {outer} contains {inner}; mount them as siblings"
                )

""".github/workflows/deploy-app.yml: the invariants a workflow file cannot test.

Nothing here runs GitHub Actions - actionlint runs in CI and the workflow only
executes on the box - so what is checked is the shape of the file: which
triggers can reach the self-hosted runner, which lane waits for an approval,
and what the rollback step is gated on.

Every assertion stands for a way this pipeline can be wrong quietly. A deploy
that rolls back when it should not, or a migration that reaches production
unapproved, both look like an ordinary green run until someone reads the file.

PyYAML parses the `on:` key as the boolean True - YAML 1.1's "yes/no/on/off"
rule - so the trigger block is `wf[True]`, not `wf["on"]`.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
DEPLOY_APP = WORKFLOWS / "deploy-app.yml"
REGISTRY_DOC = ROOT / "docs" / "registry.md"

SELF_HOSTED = "self-hosted"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def workflow() -> dict:
    return load(DEPLOY_APP)


# The jobs that run on the box. Everything else - `classify`, `verify-gate` -
# decides on GitHub whether they may.
DECIDERS = {"classify", "verify-gate"}


def deploy_jobs(wf: dict) -> dict:
    """The two lanes: every job that runs on the box."""
    return {name: job for name, job in wf["jobs"].items() if name not in DECIDERS}


def run_steps(job: dict) -> list[dict]:
    return [step for step in job["steps"] if "run" in step]


# --- the trigger ------------------------------------------------------------


def test_the_reusable_workflow_is_not_callable_from_a_pull_request():
    # A fork's pull request executing on a machine in a house is the standard
    # catastrophe, and this workflow is what would run it. Every repository in
    # this organisation is public, so the fork does not even need access.
    wf = workflow()
    assert set(wf[True]) == {"workflow_call"}


def test_no_workflow_here_lets_a_pull_request_reach_the_self_hosted_runner():
    # The guard one file wider: the rule is about the runner, not about this
    # file, and the next workflow added to this directory is the one nobody
    # will think to check.
    checked = set()
    # *.y*ml, not *.yml: GitHub reads both extensions, and this guard
    # exists for the next workflow nobody thinks to check - which is exactly
    # the one that might be spelled .yaml.
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        wf = load(path)
        # By the jobs' `runs-on`, not by a text search: ci.yml says
        # "self-hosted" in the comment explaining that it never uses one, and
        # a grep of the file calls that a violation.
        targets = str([job.get("runs-on") for job in wf["jobs"].values()])
        if SELF_HOSTED not in targets and "inputs.runs_on" not in targets:
            continue
        checked.add(path.name)
        assert "pull_request" not in set(wf[True]), path.name
        assert "pull_request_target" not in set(wf[True]), path.name
    # The detection has to find the one workflow that does reach the box, or
    # this test passes by looking at nothing.
    assert "deploy-app.yml" in checked, checked


def test_the_workflows_directory_was_actually_searched():
    # The guard on the guard: a glob that matches nothing passes the test
    # above without reading a line.
    names = {p.name for p in WORKFLOWS.glob("*.y*ml")}
    assert {"ci.yml", "deploy-app.yml"} <= names, names


# --- the inputs -------------------------------------------------------------


def test_it_takes_the_app_by_name_and_nothing_else_is_required():
    inputs = workflow()[True]["workflow_call"]["inputs"]
    assert inputs["app"]["required"] is True
    assert inputs["app"]["type"] == "string"
    optional = {name for name, spec in inputs.items() if name != "app"}
    for name in optional:
        assert inputs[name]["required"] is False, name
        assert "default" in inputs[name], name
    assert "runs_on" in optional


def test_the_runner_default_is_the_box_and_both_lanes_use_the_input():
    wf = workflow()
    default = yaml.safe_load(wf[True]["workflow_call"]["inputs"]["runs_on"]["default"])
    assert SELF_HOSTED in default
    for name, job in deploy_jobs(wf).items():
        assert job["runs-on"] == "${{ fromJSON(inputs.runs_on) }}", name


def test_classify_runs_on_github_rather_than_the_box():
    # It needs only the registry and the push diff, and it is what decides
    # whether the owner must approve before anything touches production - so
    # it must not be waiting on the box's runner to be awake to decide it.
    assert workflow()["jobs"]["classify"]["runs-on"] == "ubuntu-latest"


# --- concurrency ------------------------------------------------------------


def test_concurrency_is_per_app_and_never_cancels():
    concurrency = workflow()["concurrency"]
    # Per app. NOT because it lets two apps deploy at once - a concurrency
    # group is already scoped to its repository and each app has its own, so
    # two apps never shared a group. What naming the app buys is that this
    # group cannot collide with another in the SAME repository, and that a
    # queued run says which app it is waiting for.
    assert "inputs.app" in concurrency["group"], concurrency["group"]
    assert concurrency["group"] == "deploy-${{ inputs.app }}"
    # A cancelled run can leave the box between `git pull` and
    # `up -d --build`, which is a state no exit code describes.
    assert concurrency["cancel-in-progress"] is False


# --- the two lanes ----------------------------------------------------------


def test_there_are_exactly_two_lanes_and_they_are_mutually_exclusive():
    wf = workflow()
    lanes = deploy_jobs(wf)
    assert set(lanes) == {"deploy", "deploy-migration"}
    for name, job in lanes.items():
        needs = job["needs"]
        assert "classify" in ([needs] if isinstance(needs, str) else needs), name
    assert lanes["deploy"]["if"] == "needs.classify.outputs.migration == 'false'"
    assert (
        lanes["deploy-migration"]["if"] == "needs.classify.outputs.migration == 'true'"
    )


def test_the_migration_lane_waits_for_the_owner():
    # `environment: production` is the whole gate: it carries the required
    # reviewer. Without it the job runs, and a migration is the only class of
    # change that can destroy data.
    wf = workflow()
    assert wf["jobs"]["deploy-migration"]["environment"] == "production"
    # And the other lane must NOT have it, or every deploy needs a tap and the
    # approval stops meaning anything.
    assert "environment" not in wf["jobs"]["deploy"]


def test_the_migration_lane_will_not_run_until_the_gate_is_proven_to_exist():
    # `environment: production` is not self-enforcing: referencing an
    # environment that does not exist creates it, with no protection rules,
    # and runs the job. So the gate is only real if something CHECKS that the
    # environment has a required reviewer - and that check has to be its own
    # job, because a step inside deploy-migration runs after the approval and
    # could only ever verify a gate that already worked.
    wf = workflow()
    needs = wf["jobs"]["deploy-migration"]["needs"]
    assert "verify-gate" in needs, needs

    gate = wf["jobs"]["verify-gate"]
    # On GitHub, and without the environment itself - a gate job that waited
    # at the gate it is checking is no gate.
    assert gate["runs-on"] == "ubuntu-latest"
    assert "environment" not in gate
    # Only when a migration is actually being deployed; otherwise every
    # ordinary deploy of every app would need the environment configured.
    assert gate["if"] == "needs.classify.outputs.migration == 'true'"

    body = "\n".join(step["run"] for step in run_steps(gate))
    assert "environments/production" in body
    assert "required_reviewers" in body
    assert "exit 1" in body


def test_the_approval_travels_to_the_box():
    # bin/deploy re-checks against the box's own HEAD and refuses without
    # MIGRATION_APPROVED, so the approval has to arrive as a variable rather
    # than staying in GitHub's audit log.
    wf = workflow()
    gated = run_steps(wf["jobs"]["deploy-migration"])[0]
    assert gated["env"]["MIGRATION_APPROVED"] == "1"
    # The ungated lane must never set it: that would hand the re-check the
    # answer it exists to withhold.
    for step in run_steps(wf["jobs"]["deploy"]):
        assert "MIGRATION_APPROVED" not in step.get("env", {}), step.get("name")


def test_neither_lane_checks_out_anything_on_the_box():
    # The runner's workspace is not the deploy target. A deploy from it comes
    # up on a brand-new empty volume while the real data sits in the old one,
    # which looks exactly like data loss.
    for name, job in deploy_jobs(workflow()).items():
        for step in job["steps"]:
            assert "uses" not in step, f"{name}: {step}"


# --- the rollback is gated on exit 2, not on failure ------------------------


def test_the_rollback_runs_on_exit_two_and_only_on_exit_two():
    # Exit 2 means the deploy RAN and is unhealthy: the database may have been
    # migrated and the previous image is the way back. Exit 1 is a refusal to
    # start - wrong branch, no .env, an unapproved migration - which leaves
    # production untouched and still serving, and where rolling back would
    # take a working site down to "recover" from nothing. `if: failure()`
    # alone cannot tell those apart, and this is both lanes' most expensive
    # mistake.
    for name, job in deploy_jobs(workflow()).items():
        steps = run_steps(job)
        deploy, rollback = steps[0], steps[1]
        assert deploy["id"] == "deploy", name
        assert "bin/rollback" in rollback["run"], name
        assert rollback["if"] == "failure() && steps.deploy.outputs.rc == '2'", name
        assert rollback["if"] != "failure()", name


def test_the_deploy_step_publishes_the_exit_code_it_is_gated_on():
    # The gate above reads steps.deploy.outputs.rc, which exists only because
    # the step captures the code instead of letting the failure end it. A step
    # that simply failed would report no rc, the `if` would never match, and
    # an unhealthy deploy would sit there un-rolled-back.
    for name, job in deploy_jobs(workflow()).items():
        body = run_steps(job)[0]["run"]
        assert "rc=0" in body, name
        assert "|| rc=$?" in body, name
        assert 'echo "rc=${rc}" >> "$GITHUB_OUTPUT"' in body, name
        assert 'exit "${rc}"' in body, name


# --- classify ---------------------------------------------------------------


def test_classify_gates_whenever_it_cannot_tell():
    # The safe default is the gated lane: a needless approval costs one tap,
    # and a migration deployed unattended is the failure this pipeline must
    # not have. Every uncertain branch goes through one helper so that the
    # default cannot be forgotten in a branch added later.
    body = classify_script()
    assert "gated()" in body
    for uncertainty in (
        "0000000000000000000000000000000000000000",  # no comparable range
        "Could not read the registry",  # registry unreadable
        "is not an executable file",  # hook missing or not runnable
        "added failed",  # hook could not answer
    ):
        assert uncertainty in body, uncertainty
    # "I could not tell" and "there were none" are opposite answers, and only
    # the second one may reach the ungated lane.
    assert body.count("migration=false") == 2, body.count("migration=false")


def test_classify_asks_the_registry_and_the_app_rather_than_grepping_paths():
    # The platform does not know any app's migration tool or layout. The
    # registry says whether the app has a schema at all; the app's own hook
    # says what this push adds. A path pattern here would be one app's.
    body = classify_script()
    assert "apps.yml" in body
    assert 'entry["migrations"]' in body
    assert "deploy/migrations added" in body
    assert "alembic" not in body.lower()


def test_classify_never_calls_the_hook_bare():
    # Under `set -e` the hook's exit status would become this step's, and a
    # hook that failed would abort the job rather than gating the deploy.
    body = classify_script()
    line = [ln for ln in body.splitlines() if "deploy/migrations added" in ln][0]
    assert line.strip().startswith("if ! "), line


def test_classify_clones_enough_history_to_answer():
    # The hook is asked about before...after. A shallow clone does not contain
    # `before`, so the hook would fail and every deploy would take the gated
    # lane - correct, and useless.
    checkouts = [s for s in workflow()["jobs"]["classify"]["steps"] if "uses" in s]
    app = [s for s in checkouts if s["with"].get("path") == "app"][0]
    assert app["with"]["fetch-depth"] == 0


def test_the_classify_outputs_are_wired_to_the_step_that_sets_them():
    # Delete this mapping and both lanes compare against an empty string,
    # both `if`s are false, both jobs skip - and the run is GREEN with
    # nothing deployed. Nothing else in this file would notice.
    outputs = workflow()["jobs"]["classify"]["outputs"]
    assert outputs["migration"] == "${{ steps.check.outputs.migration }}"
    # And the step it names is the one that writes it.
    assert "migration=" in classify_step()["run"]


def test_classify_installs_the_only_thing_its_parser_needs():
    # PyYAML's presence on ubuntu-latest is an image detail, not a promise.
    # Without it the registry lookup fails, gated() fires, and every deploy
    # of every app takes the approval lane permanently - in a green run.
    steps = workflow()["jobs"]["classify"]["steps"]
    positions = [i for i, s in enumerate(steps) if "pip install" in s.get("run", "")]
    assert positions, [s.get("name") for s in steps]
    assert "PyYAML" in steps[positions[0]]["run"]
    # Before the step that imports it.
    check = [i for i, s in enumerate(steps) if s.get("id") == "check"][0]
    assert positions[0] < check


def test_classify_makes_an_uncertain_answer_visible_in_the_run_summary():
    # The gated branch is correct and quiet. A deploy that takes the approval
    # lane because PyYAML was missing looks exactly like one that takes it
    # because a migration is real.
    assert 'echo "::warning::$1"' in classify_script()


def test_classify_exports_platform_dir_to_the_hook():
    # The contract says the hook is called with PLATFORM_DIR exported, and
    # bin/deploy and bin/rollback both do it. A hook that reads it would
    # otherwise fail here only - on the runner - and every deploy of that app
    # would take the approval lane for good.
    assert classify_step()["env"]["PLATFORM_DIR"] == "${{ github.workspace }}/platform"


def test_neither_lane_carries_a_token_it_does_not_use():
    # Both jobs' whole act is running a shell script on the box. Without an
    # explicit empty block they inherit the CALLER repository's default token,
    # on a machine in a house, for nothing.
    for name, job in deploy_jobs(workflow()).items():
        assert job["permissions"] == {}, name


def test_the_deploy_step_records_which_platform_checkout_ran():
    # classify read apps.yml from platform@main; the box runs its own
    # checkout, which can be months behind. When the two disagree, this line
    # is the only place that says so.
    for name, job in deploy_jobs(workflow()).items():
        assert "git rev-parse --short HEAD" in run_steps(job)[0]["run"], name


def test_a_frozen_rollback_is_distinguishable_from_an_ordinary_failure():
    # bin/rollback exits 3 when it stopped part-way and a human must decide
    # about the dump. Without this the step is red like any other red step,
    # and a frozen app is something nobody is told about.
    for name, job in deploy_jobs(workflow()).items():
        body = run_steps(job)[1]["run"]
        assert '[ "${rc}" -eq 3 ]' in body, name
        assert "::error::" in body, name
        assert "pre-deploy dump" in body, name
        # And the step still fails: an annotation is not an outcome.
        assert 'exit "${rc}"' in body, name


def classify_step() -> dict:
    steps = [s for s in workflow()["jobs"]["classify"]["steps"] if s.get("id") == "check"]
    assert len(steps) == 1
    return steps[0]


def classify_script() -> str:
    return classify_step()["run"]


# --- nothing is one app's ---------------------------------------------------


def test_no_shell_in_the_workflow_names_a_particular_app():
    # The single-app workflow this replaces hard-coded ~/anime_site and
    # deploy/deploy.sh. Generalising it must not leave one app's path in a
    # command that every app now runs.
    for job in workflow()["jobs"].values():
        for step in run_steps(job):
            body = "\n".join(
                line
                for line in step["run"].splitlines()
                if not line.lstrip().startswith("#")
            )
            for name in ("anime_site", "media", "travel"):
                assert name not in body, step.get("name", step.get("id"))


def test_it_calls_the_platform_scripts_from_the_platform_checkout():
    for name, job in deploy_jobs(workflow()).items():
        for step in run_steps(job):
            assert 'cd "${PLATFORM_DIR:-$HOME/cg1618}"' in step["run"], name
        assert "./bin/deploy" in run_steps(job)[0]["run"], name


# --- the shell parses -------------------------------------------------------


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


def test_every_run_block_parses():
    # actionlint runs in CI and checks the workflow's own syntax; it does not
    # run the shell. An unbalanced quote in a run block is only discovered on
    # the box, mid-deploy, otherwise.
    exe = usable_bash()
    if exe is None:
        pytest.skip("no working bash on this machine")
    for job in workflow()["jobs"].values():
        for step in run_steps(job):
            script = Path(tempfile.gettempdir()) / "cg1618-run-block.sh"
            script.write_text(step["run"], encoding="utf-8", newline="\n")
            subprocess.run([exe, "-n", str(script)], check=True)


# --- the caller ------------------------------------------------------------


def caller_example() -> dict:
    """The worked example an app copies, out of the registry doc.

    It lives there rather than in an app repository because the platform
    cannot edit those, and because an app that copies something wrong here
    hands the fork-on-the-box catastrophe straight back.
    """
    text = REGISTRY_DOC.read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)
    callers = [b for b in blocks if "deploy-app.yml" in b]
    assert len(callers) == 1, f"{len(callers)} caller examples in registry.md"
    return yaml.safe_load(callers[0])


def test_the_documented_caller_calls_this_workflow_with_the_app_name():
    caller = caller_example()
    job = next(iter(caller["jobs"].values()))
    assert job["uses"].startswith(
        "cg1618-apps/platform/.github/workflows/deploy-app.yml@"
    )
    assert job["with"]["app"]
    # Everything the reusable workflow decides stays there. A caller that
    # restates the runner or the concurrency group has forked the policy.
    assert "runs-on" not in job
    assert "concurrency" not in caller

    required = {
        name
        for name, spec in workflow()[True]["workflow_call"]["inputs"].items()
        if spec["required"]
    }
    assert required <= set(job["with"]), required


def test_the_documented_caller_deploys_main_and_only_main():
    # main is production and the box's checkout of the app tracks main, so
    # this trigger and that checkout are the same decision stated twice. A
    # pull_request trigger here would reach the self-hosted runner through
    # the called workflow.
    caller = caller_example()
    assert set(caller[True]) == {"push"}
    assert caller[True]["push"]["branches"] == ["main"]

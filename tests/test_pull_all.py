"""pull-all.ps1: one pull for the platform and every app cloned inside it.

The script runs only on Windows PowerShell, so these assert what it must
never stop doing rather than executing it.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PULL_ALL = ROOT / "pull-all.ps1"
PULL_ALL_CMD = ROOT / "pull-all.cmd"


def test_it_only_ever_fast_forwards():
    """A pull that needs a merge is refused, never resolved here.

    Five repositories at once is exactly when a merge commit nobody chose would
    go unnoticed in the scroll.
    """
    body = PULL_ALL.read_text(encoding="utf-8")
    assert "pull --ff-only" in body
    assert "rebase" not in body


def test_it_reads_the_app_list_from_the_registry():
    """An app added to apps.yml is pulled without anyone editing this script.

    And an entry with `repo: null` - `logs`, platform-owned - is skipped,
    because there is no checkout of it to pull.
    """
    body = PULL_ALL.read_text(encoding="utf-8")
    assert "apps.yml" in body
    assert "'null'" in body
    for app in ("media", "food", "travel", "art"):
        assert f"'{app}'" not in body


def test_it_never_switches_a_branch():
    """Each repository is pulled on its own branch.

    Checking out dev would move HEAD under any session working in that
    directory, mid-edit, with no warning to it.
    """
    body = PULL_ALL.read_text(encoding="utf-8")
    # The two ways it calls git: `& git -C $repo.Path <verb>` and
    # Get-Git with an argument array. "checkout" also appears in prose.
    for verb in ("checkout", "switch"):
        assert f"$repo.Path {verb}" not in body
        assert f"'{verb}'" not in body


def test_the_one_click_wrapper_exists_and_only_delegates():
    assert PULL_ALL_CMD.is_file()
    body = PULL_ALL_CMD.read_text(encoding="utf-8")
    assert "pull-all.ps1" in body
    assert "-ExecutionPolicy Bypass" in body
    assert "%*" in body
    assert "pause" in body


def test_the_wrapper_passes_the_exit_code_through():
    """`endlocal` then `exit /b %RC%` on the next line always exits 0.

    endlocal discards RC before the next line is expanded, so a failed pull
    would read as success to anything checking the exit code. On one line, the
    expansion happens first.
    """
    body = PULL_ALL_CMD.read_text(encoding="utf-8")
    assert "endlocal & exit /b %RC%" in body

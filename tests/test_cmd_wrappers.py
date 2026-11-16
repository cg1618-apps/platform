"""The one-click .cmd wrappers at the repository root.

Each one exists so Explorer can run a .ps1 on a double-click, and each one
must hand the script's exit code back to whatever ran it.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = sorted(ROOT.glob("*.cmd"))


def test_there_are_wrappers_to_check():
    """Otherwise the parametrised test below passes on an empty list."""
    assert WRAPPERS


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=lambda p: p.name)
def test_the_exit_code_survives_endlocal(wrapper):
    """`endlocal` then `exit /b %RC%` on the next line always exits 0.

    endlocal discards RC before the next line is expanded, so a failed script
    reads as success to anything checking the exit code. On one line, the
    expansion happens first.
    """
    lines = [line.strip() for line in wrapper.read_text(encoding="utf-8").splitlines()]
    assert "endlocal & exit /b %RC%" in lines
    assert "endlocal" not in lines
